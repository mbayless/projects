# Projects

Security learning projects. Each folder stands on its own and has its own README with step-by-step setup.

| Project | What it does | Needs |
|---|---|---|
| [threat-arena](threat-arena/) | Live map of bot attacks, with a plain-English explanation of each one. Starts on sample data | Python 3.10+ |
| [sentinel-terraform](sentinel-terraform/) | Microsoft Sentinel and its analytics rules as code, deployed by GitHub Actions | Azure subscription, Terraform, Azure CLI, GitHub CLI |
| [phi-scanner](phi-scanner/) | Finds health and personal data in files and links, with a manual review step | Python 3 |

```bash
git clone https://github.com/mbayless/projects.git
cd projects/threat-arena && ./run     # quickest one to try
```
