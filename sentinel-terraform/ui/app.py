"""Sentinel Terraform UI: validate, plan and manage analytics rules from the browser.

Run:  ./sentinel ui     (or: streamlit run ui/app.py)

Every action shows the real command and what it does before running it, so you
can run the same thing by hand later. There is deliberately no apply: deployments
go through GitHub Actions (see CLAUDE.md).
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
TF_DIR = ROOT / "terraform"
RULES_DIR = ROOT / "rules"
REPO_ROOT = ROOT.parent
RESOURCE_GROUP = "rg-sentinel-lab"
PROVIDERS = ["Microsoft.OperationalInsights", "Microsoft.SecurityInsights",
             "Microsoft.OperationsManagement", "Microsoft.Insights"]
TF_ENV = {**os.environ, "TF_INPUT": "0"}

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


def stream(cmd, shown, what, cwd=TF_DIR):
    """Show the command, run it, and stream its output live. Returns (code, output)."""
    explain(shown, what)
    box = st.empty()
    lines = []
    proc = subprocess.Popen(cmd, cwd=cwd, env=TF_ENV, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in proc.stdout:
        lines.append(line)
        box.code("".join(lines)[-30000:] or " ", language=None)
    proc.wait()
    out = "".join(lines)
    if not out:
        box.code("(no output)", language=None)
    return proc.returncode, out


def ensure_init():
    if (TF_DIR / ".terraform").is_dir():
        return True
    code, _ = stream(["terraform", "init", "-no-color"], "terraform init",
                     "Downloads the azurerm provider and sets up the state backend. Needed once per folder.")
    return code == 0


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


def show_plan_result(out, code):
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
    st.info("Nothing in Azure changed. To deploy, open a pull request; GitHub Actions runs the apply.")


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

tab_plan, tab_validate, tab_rules, tab_deploy, tab_status = st.tabs(
    ["📋 Plan", "✅ Validate", "📜 Rules", "🚀 Deploy", "🩺 Status"])

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

    st.markdown("**Uncommitted changes** in `sentinel-terraform/`")
    explain("git status --short sentinel-terraform", "Lists files you've changed but not committed yet.")
    code, out = quiet(["git", "status", "--short", "sentinel-terraform"], cwd=REPO_ROOT)
    st.code(out or "(nothing to commit)", language=None)

    st.markdown("**Open a pull request.** Run these in the VS Code terminal from `projects/`:")
    st.code("git checkout -b rule/<name>\n"
            "git add sentinel-terraform\n"
            "git status            # check: no tfstate, tfplan, plan.txt or *_override.tf files\n"
            'git commit -m "Describe the change"\n'
            "git push -u origin rule/<name>\n"
            "gh pr create --fill", language="bash")

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

# --- Status -------------------------------------------------------------------

with tab_status:
    st.subheader("Tools and Azure")
    for tool, pkg in [("terraform", "terraform"), ("az", "azure-cli"), ("gh", "gh")]:
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
