import os
import json
from github import Github, Auth


# -------------------------------------------------
# Configuration
# -------------------------------------------------
AGENT_CHECK_NAME = "AI PR Review Agent"


# -------------------------------------------------
# Authenticate with GitHub
# -------------------------------------------------
token = os.getenv("GITHUB_TOKEN")
if not token:
    raise RuntimeError("GITHUB_TOKEN is not set")

g = Github(auth=Auth.Token(token))


# -------------------------------------------------
# Read PR context dynamically from GitHub Actions
# -------------------------------------------------
event_path = os.getenv("GITHUB_EVENT_PATH")
if not event_path:
    raise RuntimeError("GITHUB_EVENT_PATH is not set")

with open(event_path, "r") as f:
    event = json.load(f)

if "pull_request" not in event:
    raise RuntimeError("Workflow was not triggered by a pull request")

repo_name = event["repository"]["full_name"]
pr_number = event["pull_request"]["number"]

pr_author = event["pull_request"]["user"]["login"]
workflow_actor = event["sender"]["login"]


# -------------------------------------------------
# Evaluate CI checks using GitHub Checks API
# -------------------------------------------------
def check_pr_status(repo_name, pr_number):
    repo = g.get_repo(repo_name)
    pr = repo.get_pull(pr_number)

    latest_commit = pr.get_commits().reversed[0]
    check_runs = latest_commit.get_check_runs()

    if check_runs.totalCount == 0:
        print("No CI checks found. Waiting...")
        return "waiting"

    print(f"Evaluating CI checks for PR #{pr_number}...\n")

    for check in check_runs:
        print(
            f"Check: {check.name} | "
            f"Status: {check.status} | "
            f"Conclusion: {check.conclusion}"
        )

        # 🚫 Ignore agent's own job
        if check.name == AGENT_CHECK_NAME:
            continue

        if check.status != "completed":
            return "waiting"

        if check.conclusion in ["failure", "cancelled", "timed_out"]:
            return "blocked"

    return "approved"


# -------------------------------------------------
# Act on PR based on agent decision
# -------------------------------------------------
def review_pr(repo_name, pr_number, decision):
    repo = g.get_repo(repo_name)
    pr = repo.get_pull(pr_number)

    # ✅ CI passed
    if decision == "approved":

        # 👤 Same author reviewing own PR
        if pr_author == workflow_actor:
            pr.create_review(
                body=(
                    "✅ **All CI checks passed**\n\n"
                    "🤖 **AI Agent Review Result:** Approved\n\n"
                    "ℹ️ *PR author and reviewer are the same. "
                    "GitHub does not allow self-approval, so a comment is added instead.*\n\n"
                    "🚀 **This PR is safe to merge.**"
                ),
                event="COMMENT",
            )
            print("Self-review detected. Approval-equivalent comment added.")
            return

        # 👥 Different reviewer → real approval
        pr.create_review(
            body="✅ All CI checks passed. PR approved by AI Agent.",
            event="APPROVE",
        )
        print("PR approved.")

    elif decision == "blocked":
        pr.create_review(
            body="❌ CI checks failed. Please address the issues and update the PR.",
            event="REQUEST_CHANGES",
        )
        print("PR blocked.")

    else:
        pr.create_review(
            body="⏳ CI checks are still running. PR under review.",
            event="COMMENT",
        )
        print("PR is still under review.")


# -------------------------------------------------
# Agent execution loop
# -------------------------------------------------
def trigger_agent_review():
    print(
        f"Starting AI-powered PR review for {repo_name} (PR #{pr_number})...\n"
    )

    pr_status = check_pr_status(repo_name, pr_number)
    review_pr(repo_name, pr_number, pr_status)


# -------------------------------------------------
# Entry point
# -------------------------------------------------
if __name__ == "__main__":
    trigger_agent_review()
