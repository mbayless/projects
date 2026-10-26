"""Sentinel Terraform UI: validate, plan and manage analytics rules from the browser.

Run:  ./sentinel ui     (or: streamlit run ui/app.py)

Every action shows the real command and what it does before running it, so you
can run the same thing by hand later. There is deliberately no apply: deployments
go through GitHub Actions (see CLAUDE.md).
"""
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
TF_DIR = ROOT / "terraform"
STATE_DIR = ROOT / "state-storage"
STATE_RG = "rg-terraform-state"
GITHUB_REPO = "mbayless/projects"
RULES_DIR = ROOT / "rules"
REPO_ROOT = ROOT.parent
RESOURCE_GROUP = "rg-sentinel-lab"
PROVIDERS = ["Microsoft.OperationalInsights", "Microsoft.SecurityInsights",
             "Microsoft.OperationsManagement", "Microsoft.Insights"]
TF_ENV = {**os.environ, "TF_INPUT": "0", "GIT_TERMINAL_PROMPT": "0"}  # fail, never hang, on a prompt

st.set_page_config(page_title="Sentinel Terraform", page_icon="🛡️", layout="wide")


# --- Helpers ------------------------------------------------------------------

def have(tool):
    return shutil.which(tool) is not None


def quiet(cmd, cwd=ROOT):
    """Run a read-only command and return (exit code, stdout). Stderr is dropped."""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


@st.cache_data(ttl=60, show_spinner=False)
def azure_account():
    if not have("az"):
        return None
    code, out = quiet(["az", "account", "show", "-o", "json"])
    return json.loads(out) if code == 0 and out else None


def backend_mode():
    if (TF_DIR / "backend_override.tf").exists():
        return "Local file (terraform/terraform.tfstate)"
    return "Azure storage (shared with GitHub Actions)"


def explain(shown, what):
    st.markdown(f"**▶ `{shown}`**")
    st.caption(what)


def stream(cmd, shown, what, cwd=TF_DIR, answer=None):
    """Show the command, run it, and stream its output live. Returns (code, output).

    answer is typed into the command's input, e.g. "y" for a confirmation prompt.
    """
    explain(shown, what)
    box = st.empty()
    lines = []
    proc = subprocess.Popen(cmd, cwd=cwd, env=TF_ENV, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, stdin=subprocess.PIPE)
    proc.stdin.write(f"{answer}\n" if answer else "")
    proc.stdin.close()
    for line in proc.stdout:
        lines.append(line)
        box.code("".join(lines)[-30000:] or " ", language=None)
    proc.wait()
    out = "".join(lines)
    if not out:
        box.code("(no output)", language=None)
    return proc.returncode, out


def ensure_init(folder=TF_DIR):
    if (folder / ".terraform").is_dir():
        return True
    code, _ = stream(["terraform", "init", "-no-color"], "terraform init",
                     "Downloads the azurerm provider and sets up the state backend. Needed once per folder.",
                     cwd=folder)
    return code == 0


def state_storage():
    """Outputs of state-storage/ ({} until it's applied) and what its local state holds."""
    code, out = quiet(["terraform", "output", "-json"], cwd=STATE_DIR)
    outputs = {k: v.get("value") for k, v in json.loads(out).items()} if code == 0 and out else {}
    managed = quiet(["terraform", "state", "list"], cwd=STATE_DIR)[1].splitlines()
    return outputs, managed


def show_last(key):
    """Re-show a previous run's output after Streamlit reruns the page."""
    last = st.session_state.get(key)
    if last:
        with st.expander(f"Output of the last run: `{last['shown']}`", expanded=False):
            st.code(last["out"] or "(no output)", language=None)


# --- Rules --------------------------------------------------------------------

def rule_field(text, key):
    m = re.search(rf"^{key}:[ \t]*(.*?)[ \t]*$", text, re.M)
    return m.group(1) if m else ""


def rule_files():
    return sorted(f for f in RULES_DIR.glob("*.yaml") if not f.name.startswith("_"))


def rules_table():
    rows = []
    for f in rule_files():
        text = f.read_text()
        rows.append({
            "id": rule_field(text, "id"),
            "kind": rule_field(text, "kind"),
            "severity": rule_field(text, "severity"),
            "name": rule_field(text, "display_name"),
            "enabled": rule_field(text, "enabled") != "false",
            "file": f"rules/{f.name}",
        })
    return rows


# --- Plan parsing -------------------------------------------------------------

CHANGE_RE = re.compile(r"^\s*# (\S+) (?:will be|must be) (created|updated in-place|destroyed|replaced"
                       r"|read during apply)", re.M)
SUMMARY_RE = re.compile(r"Plan: (\d+) to add, (\d+) to change, (\d+) to destroy")
ACTION_LABEL = {"created": "➕ create", "updated in-place": "✏️ update", "destroyed": "🗑️ destroy",
                "replaced": "♻️ replace", "read during apply": "👁️ read"}


def show_plan_result(out, code, pipeline_note=True):
    if code != 0:
        st.error("Plan failed. The error is in the output above.")
        return
    if "No changes." in out:
        st.success("No changes. Azure already matches the code.")
        return
    m = SUMMARY_RE.search(out)
    if m:
        add, change, destroy = (int(x) for x in m.groups())
        c1, c2, c3 = st.columns(3)
        c1.metric("To add", add)
        c2.metric("To change", change)
        c3.metric("To destroy", destroy)
        if destroy:
            st.warning("This plan destroys resources. Check the list below before you open a pull request.")
    changes = [{"resource": addr, "action": ACTION_LABEL.get(act, act)} for addr, act in CHANGE_RE.findall(out)]
    if changes:
        st.dataframe(changes, hide_index=True, width="stretch")
    if pipeline_note:
        st.info("Nothing in Azure changed. To deploy, open a pull request; GitHub Actions runs the apply.")


# --- Pull request -------------------------------------------------------------

# Paths a Sentinel pull request may contain, relative to the projects repo.
PR_PATHS = ["sentinel-terraform", ".github/workflows/sentinel.yml"]
# Local-only files that must never be committed. .gitignore should already stop them.
FORBIDDEN_RE = re.compile(r"(\.tfstate|tfplan|plan\.txt|_override\.tf|\.terraform/|\.venv/)")


def open_pull_request(current, branch, message):
    """Branch, commit, push and open a PR, showing each command. Stops at the first failure."""
    def step(cmd, what):
        code, out = stream(cmd, shlex.join(cmd), what, cwd=REPO_ROOT)
        log.append(f"$ {shlex.join(cmd)}\n{out}")
        if code != 0:
            st.error("That step failed. The error is above; nothing after it ran.")
        return code == 0, out

    log = []
    if current != branch:
        if quiet(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=REPO_ROOT)[0] == 0:
            st.error(f"Branch {branch} already exists. Pick a new name, or switch to it in the terminal first.")
            return
        if not step(["git", "checkout", "-b", branch],
                    "Creates a new branch from where you are and switches to it. Your changes come along.")[0]:
            return
    if not step(["git", "add", *PR_PATHS], "Stages the Sentinel files for the commit.")[0]:
        return

    staged = quiet(["git", "diff", "--cached", "--name-only"], cwd=REPO_ROOT)[1].splitlines()
    outside = [f for f in staged if not any(f == p or f.startswith(p + "/") for p in PR_PATHS)]
    secret = [f for f in staged if FORBIDDEN_RE.search(f)]
    if outside or secret:
        quiet(["git", "reset", "-q", *staged], cwd=REPO_ROOT)
        st.error("Stopped before committing, and unstaged everything. These files must not go in this commit:\n\n"
                 + "\n".join(f"- `{f}`" for f in outside + secret))
        return
    st.markdown("**Files in this commit:**\n" + "\n".join(f"- `{f}`" for f in staged))

    if not step(["git", "commit", "-m", message], "Saves the staged files as one commit on this branch.")[0]:
        return
    if not step(["git", "push", "-u", "origin", branch],
                "Uploads the branch to GitHub. This does not deploy anything.")[0]:
        return
    ok, out = step(["gh", "pr", "create", "--base", "main", "--head", branch, "--title", message,
                    "--body", "Opened from the Sentinel Terraform UI. The Plan job posts the plan below."],
                   "Opens the pull request. GitHub Actions then runs the plan and comments it here.")
    if ok:
        url = out.strip().splitlines()[-1] if out.strip() else ""
        st.session_state["pr"] = {"shown": "commit, push and open pull request", "out": "\n".join(log), "url": url}
        st.success(f"Pull request opened: {url}")
        st.info("Next: wait for the Plan comment on the pull request, check it, then merge. "
                "The Apply job waits for approval in the production environment.")


# --- Sidebar ------------------------------------------------------------------

account = azure_account()
with st.sidebar:
    st.header("🛡️ Sentinel Terraform")
    if account:
        st.success(f"Azure: **{account.get('name')}**\n\n{account.get('user', {}).get('name', '')}", icon="✅")
    elif not have("az"):
        st.error("Azure CLI not installed. Run `brew install azure-cli`.")
    else:
        st.warning("Not signed in to Azure. Run `az login` in a terminal, then Refresh.")
    st.markdown(f"**State:** {backend_mode()}")
    st.markdown(f"**Initialised:** {'yes' if (TF_DIR / '.terraform').is_dir() else 'not yet'}")
    st.markdown(f"**Rules:** {len(rule_files())}")
    if st.button("Refresh", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Deploying happens through GitHub Actions, not here.")

st.title("Sentinel Terraform")
st.caption("Check, plan and manage the Sentinel analytics rules. Each button shows the command it runs.")

tab_setup, tab_plan, tab_validate, tab_rules, tab_deploy, tab_incidents, tab_status = st.tabs(
    ["⚙️ Setup", "📋 Plan", "✅ Validate", "📜 Rules", "🚀 Deploy", "🧹 Incidents", "🩺 Status"])

# --- Setup --------------------------------------------------------------------

with tab_setup:
    st.subheader("One-time setup for the GitHub pipeline")
    st.write("Two steps, once per subscription. After that, every deploy goes through a pull request.")

    # Step 1: state storage with Terraform (its own state stays local).
    outputs, managed = state_storage()
    st.markdown("### 1. State storage")
    st.caption("`state-storage/` creates the storage account the pipeline keeps Terraform state in. "
               "Its own state stays on this Mac in `state-storage/terraform.tfstate`. Don't delete that file.")
    if outputs.get("storage_account_name"):
        st.success(f"Created: **{outputs['storage_account_name']}** in {outputs['resource_group_name']}")
    elif account is None:
        st.warning("Sign in to Azure first (`az login`), then Refresh.")
    else:
        rg_exists = quiet(["az", "group", "exists", "-n", STATE_RG])[1] == "true"
        if rg_exists and "azurerm_resource_group.state" not in managed:
            st.info(f"`{STATE_RG}` already exists in Azure. Import it first so Terraform manages it "
                    "instead of trying to create it again.")
            if st.button("Import existing resource group"):
                rg_id = f"/subscriptions/{account['id']}/resourceGroups/{STATE_RG}"
                if ensure_init(STATE_DIR):
                    cmd = ["terraform", "import", "-no-color", "azurerm_resource_group.state", rg_id]
                    code, out = stream(cmd, f"terraform import azurerm_resource_group.state {rg_id}",
                                       "Records the existing resource group in Terraform's state. "
                                       "Changes nothing in Azure.", cwd=STATE_DIR)
                    if code == 0:
                        st.success("Imported. Now run the plan.")
        else:
            if st.button("Plan state storage"):
                if ensure_init(STATE_DIR):
                    code, out = stream(["terraform", "plan", "-no-color", "-out=tfplan"],
                                       "terraform plan -out=tfplan",
                                       "Shows what would be created and saves the plan, so Apply does exactly this.",
                                       cwd=STATE_DIR)
                    st.session_state["state_plan"] = {"shown": "terraform plan", "out": out,
                                                      "code": code}
                    show_plan_result(out, code, pipeline_note=False)
            elif "state_plan" in st.session_state:
                last = st.session_state["state_plan"]
                show_last("state_plan")
                show_plan_result(last["out"], last["code"], pipeline_note=False)

            saved = st.session_state.get("state_plan", {}).get("code") == 0 and (STATE_DIR / "tfplan").exists()
            ok_apply = st.checkbox("I've read the plan above. Create these resources in Azure.",
                                   disabled=not saved)
            if st.button("Apply state storage", type="primary", disabled=not (saved and ok_apply)):
                code, out = stream(["terraform", "apply", "-no-color", "tfplan"], "terraform apply tfplan",
                                   "Creates exactly what the saved plan showed.", cwd=STATE_DIR)
                (STATE_DIR / "tfplan").unlink(missing_ok=True)
                st.session_state.pop("state_plan", None)
                if code == 0:
                    st.success("State storage created. Continue with step 2.")
                    st.button("Show step 2")
                else:
                    st.error("Apply failed. The error is above.")
            if not saved:
                st.caption("Run the plan first. Apply uses the saved plan.")

    # Step 2: bootstrap (GitHub identity, roles, repo variables).
    st.markdown("### 2. GitHub sign-in identity and repo variables")
    st.caption("`bootstrap/setup.sh` creates the `github-sentinel-terraform` identity, gives it its roles, "
               "and saves the five repo variables the pipeline needs.")
    gh_vars = set()
    if have("gh"):
        code, out = quiet(["gh", "variable", "list", "-R", GITHUB_REPO, "--json", "name"])
        if code == 0 and out:
            gh_vars = {v["name"] for v in json.loads(out)}
    needed = ["AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID", "TF_STATE_RG", "TF_STATE_STORAGE"]
    for name in needed:
        st.markdown(f"{'✅' if name in gh_vars else '⬜'} `{name}`")

    if not outputs.get("storage_account_name"):
        st.caption("Finish step 1 first.")
    elif not (have("gh") and quiet(["gh", "auth", "status"])[0] == 0):
        st.warning("Install and sign in to the GitHub CLI first: `brew install gh && gh auth login`")
    elif account is not None:
        repo = st.text_input("GitHub repo", value=GITHUB_REPO)
        location = st.text_input("Azure region", value="eastus")
        ok_boot = st.checkbox(f"Use subscription **{account.get('name')}** ({account.get('id')})")
        if st.button("Run bootstrap", type="primary", disabled=not ok_boot):
            code, out = stream(["./bootstrap/setup.sh", repo, location],
                               f"./bootstrap/setup.sh {repo} {location}",
                               "Each ==> line is one stage. Safe to re-run if it stops partway. "
                               "Your tick above answers its 'Continue with this subscription?' question.",
                               cwd=ROOT, answer="y")
            st.session_state["bootstrap"] = {"shown": "bootstrap/setup.sh", "out": out}
            if code == 0:
                st.success("Bootstrap finished. Next: add yourself as a required reviewer on the "
                           "production environment in GitHub, then open a pull request on the Deploy tab.")
            else:
                st.error("Bootstrap stopped. The error is above. Fix it and run it again.")
        else:
            show_last("bootstrap")

# --- Plan ---------------------------------------------------------------------

with tab_plan:
    st.subheader("Preview changes in Azure")
    st.write("Compares the code with what exists in Azure and lists what would be created, changed "
             f"or destroyed. Nothing in Azure changes. State: **{backend_mode()}**.")
    if not have("terraform"):
        st.error("Terraform not installed. Run `brew install terraform`.")
    elif st.button("Run plan", type="primary", disabled=account is None):
        if ensure_init():
            code, out = stream(["terraform", "plan", "-no-color"], "terraform plan",
                               "Reads the current state from Azure and prints the changes it would make.")
            st.session_state["plan"] = {"shown": "terraform plan", "out": out, "code": code}
            show_plan_result(out, code)
    elif "plan" in st.session_state:
        last = st.session_state["plan"]
        show_last("plan")
        show_plan_result(last["out"], last["code"])
    if account is None:
        st.caption("Sign in to Azure to run a plan.")

# --- Validate -----------------------------------------------------------------

with tab_validate:
    st.subheader("Check formatting and syntax")
    st.write("Runs two checks. Neither needs Azure access or changes anything.")
    if st.button("Run validate", type="primary", disabled=not have("terraform")):
        fmt_code, fmt_out = stream(["terraform", "fmt", "-check", "-recursive", "-no-color"],
                                   "terraform fmt -check -recursive",
                                   "Checks formatting. Lists any file that isn't in standard Terraform style.")
        if fmt_code == 0:
            st.success("Formatting is clean")
        else:
            st.error("The files listed need formatting. Fix with: `cd terraform && terraform fmt -recursive`")
        if ensure_init():
            val_code, val_out = stream(["terraform", "validate", "-no-color"], "terraform validate",
                                       "Checks syntax, types, and that every rule YAML parses.")
            if val_code == 0:
                st.success("Configuration is valid")
            else:
                st.error("Validation failed. The error is above.")
            st.session_state["validate"] = {"shown": "terraform fmt + validate", "out": fmt_out + val_out}
    else:
        show_last("validate")

# --- Rules --------------------------------------------------------------------

with tab_rules:
    st.subheader("Analytics rules")
    st.caption("One YAML file per rule in `rules/`. Files starting with `_` are skipped.")
    rows = rules_table()
    st.dataframe(rows, hide_index=True, width="stretch")

    if rows:
        pick = st.selectbox("View a rule", [r["file"] for r in rows])
        st.code((ROOT / pick).read_text(), language="yaml")

    with st.expander("➕ New rule from the template"):
        new_id = st.text_input("Rule id", placeholder="keyvault-deleted",
                               help="Lowercase letters, numbers and dashes. Becomes rules/<id>.yaml.")
        if st.button("Create rule file"):
            target = RULES_DIR / f"{new_id}.yaml"
            if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", new_id):
                st.error("Use lowercase letters, numbers and dashes only.")
            elif target.exists():
                st.error(f"rules/{new_id}.yaml already exists.")
            else:
                explain(f"cp rules/_template.yaml rules/{new_id}.yaml",
                        "Copies the template to a new rule file and sets its id.")
                text = (RULES_DIR / "_template.yaml").read_text()
                target.write_text(re.sub(r"^id: my-new-rule$", f"id: {new_id}", text, flags=re.M))
                st.success(f"Created rules/{new_id}.yaml")
                st.markdown("**Next:**\n"
                            "1. Edit it in VS Code: display_name, description, severity, query, tactics, entities.\n"
                            "2. Test the KQL query in the Sentinel workspace under **Logs**.\n"
                            "3. Run **Validate**, then **Plan**. Expect 1 to add.\n"
                            "4. Commit on a branch and open a pull request.")

# --- Deploy -------------------------------------------------------------------

with tab_deploy:
    st.subheader("Deploy through GitHub Actions")
    st.write("Applies run in GitHub, not on this Mac: a pull request runs **plan** and posts it as a comment; "
             "merging to `main` runs **apply** after you approve it in the `production` environment.")

    workflow_at_root = (REPO_ROOT / ".github" / "workflows" / "sentinel.yml").exists()
    gh_ok = have("gh") and quiet(["gh", "auth", "status"])[0] == 0
    checks = [
        ("GitHub CLI installed and signed in", gh_ok, "brew install gh && gh auth login"),
        ("Signed in to Azure", account is not None, "az login"),
        ("Workflow moved to the repo root", workflow_at_root,
         "Ask Claude to move .github/workflows/sentinel.yml to projects/.github/workflows/ (CLAUDE.md step 5)"),
        ("Local plan uses the shared state", not (TF_DIR / "backend_override.tf").exists(),
         "After the first pipeline apply, see CLAUDE.md step 9"),
    ]
    for label, done, fix in checks:
        if done:
            st.markdown(f"✅ {label}")
        else:
            st.markdown(f"⬜ {label}  \n&nbsp;&nbsp;&nbsp;&nbsp;Next: `{fix}`")

    st.divider()
    st.markdown("### Open a pull request")
    current = quiet(["git", "branch", "--show-current"], cwd=REPO_ROOT)[1]
    st.markdown(f"Current branch: `{current or 'unknown'}`")
    explain(f"git status --short {' '.join(PR_PATHS)}", "Lists files you've changed but not committed yet.")
    changes = quiet(["git", "status", "--short", *PR_PATHS], cwd=REPO_ROOT)[1]
    st.code(changes or "(nothing to commit)", language=None)

    on_feature = current not in ("", "main")
    branch = st.text_input("Branch name", value=current if on_feature else "rule/",
                           help="A new branch for this change, e.g. rule/keyvault-deleted. Never main.")
    message = st.text_input("Commit message", placeholder="Add Key Vault deletion rule",
                            help="Also becomes the pull request title.")
    reviewed = st.checkbox("I've checked the files above and the Plan tab result")

    branch_ok = (branch not in ("", "main", "rule/")
                 and quiet(["git", "check-ref-format", "--branch", branch], cwd=REPO_ROOT)[0] == 0)
    if branch and not branch_ok:
        st.caption("Enter a valid branch name other than main, e.g. rule/keyvault-deleted.")
    ready = gh_ok and bool(changes) and branch_ok and bool(message.strip()) and reviewed
    if not gh_ok:
        st.caption("Install and sign in to the GitHub CLI to open pull requests here.")
    elif not changes:
        st.caption("No changes to send. Edit a rule or the Terraform code first.")

    if st.button("Commit, push and open pull request", type="primary", disabled=not ready):
        open_pull_request(current, branch, message.strip())
    elif "pr" in st.session_state:
        show_last("pr")
        st.success(f"Pull request: {st.session_state['pr']['url']}")

    st.markdown("**Recent pipeline runs**")
    if not gh_ok:
        st.caption("Install and sign in to the GitHub CLI to see runs here.")
    elif st.button("Load runs"):
        explain("gh run list --workflow sentinel.yml --limit 10",
                "Shows the latest runs of the Sentinel workflow on GitHub.")
        code, out = quiet(["gh", "run", "list", "--workflow", "sentinel.yml", "--limit", "10", "--json",
                           "displayTitle,headBranch,event,status,conclusion,createdAt,url"], cwd=REPO_ROOT)
        if code == 0 and out:
            st.dataframe(json.loads(out), hide_index=True, width="stretch",
                         column_config={"url": st.column_config.LinkColumn("url")})
        else:
            st.warning("No runs found. The workflow only runs once it's at the repo root and pushed.")

# --- Incidents ----------------------------------------------------------------

with tab_incidents:
    st.subheader("Close old incidents")
    st.write("Closes open Sentinel incidents created more than N days ago, with classification "
             "**Undetermined** and an \"Auto-closed\" comment. Closed incidents stay searchable; "
             "they just leave the active queue.")
    st.caption("GitHub Actions also runs this every day at 06:00 UTC with 14 days "
               "(`.github/workflows/sentinel-close-old-incidents.yml`).")
    script = "scripts/close-old-incidents.sh"
    days = st.number_input("Older than (days)", min_value=1, max_value=365, value=14, step=1)
    if not have("jq"):
        st.warning("The script needs jq. Install it with `brew install jq`, then Refresh.")
    elif account is None:
        st.caption("Sign in to Azure to see incidents.")
    else:
        c1, c2 = st.columns(2)
        if c1.button("Preview", help="Lists what would be closed. Changes nothing."):
            stream(["bash", script, "--dry-run", str(days)], f"{script} --dry-run {days}",
                   "Lists open incidents older than the cutoff. Changes nothing.", cwd=ROOT)
        ok_close = c2.checkbox(f"Close every open incident older than {days} days")
        if c2.button("Close incidents", type="primary", disabled=not ok_close):
            code, _ = stream(["bash", script, str(days)], f"{script} {days}",
                             "Closes each incident listed. If one fails, it carries on with the rest.", cwd=ROOT)
            if code == 0:
                st.success("Done.")
            else:
                st.error("Some incidents could not be closed. The errors are above.")

# --- Status -------------------------------------------------------------------

with tab_status:
    st.subheader("Tools and Azure")
    for tool, pkg in [("terraform", "terraform"), ("az", "azure-cli"), ("gh", "gh"), ("jq", "jq")]:
        if have(tool):
            st.markdown(f"✅ `{tool}` installed")
        else:
            st.markdown(f"⚠️ `{tool}` not installed: `brew install {pkg}`")

    if st.button("Check Azure", disabled=account is None):
        explain(f"az group show -n {RESOURCE_GROUP}", "Checks the resource group Terraform deploys into exists.")
        if quiet(["az", "group", "show", "-n", RESOURCE_GROUP, "-o", "none"])[0] == 0:
            st.success(f"{RESOURCE_GROUP} exists")
        else:
            st.error(f"{RESOURCE_GROUP} not found. The bootstrap creates it.")

        explain("az provider show --namespace <name> --query registrationState -o tsv",
                "Checks the Azure resource providers Sentinel needs. The bootstrap registers them.")
        for ns in PROVIDERS:
            _, state = quiet(["az", "provider", "show", "--namespace", ns, "--query", "registrationState",
                              "-o", "tsv"])
            st.markdown(f"{'✅' if state == 'Registered' else '⚠️'} {ns}: {state or 'unknown'}")
    if account is None:
        st.caption("Sign in to Azure to check the resource group and providers.")
