---
name: vercel-deploy
description: Deploy any project to Vercel instantly as a preview deployment. Use when the user wants to deploy a project to Vercel, create a preview deployment, or share a live URL for their application.
---

# Vercel Deploy

Deploy projects to Vercel with automatic framework detection and preview URLs.

## Quick Start

1. Check if Vercel CLI is installed
2. If installed: deploy directly via CLI
3. If not installed or auth fails: use fallback deploy script

## Prerequisites Check

Check whether the Vercel CLI is installed (no escalation needed):

```bash
command -v vercel
```

## Deploy via CLI (Preferred)

If `vercel` is installed, deploy with a 10-minute timeout:

```bash
vercel deploy [path] -y
```

**Important**: Use a 10 minute (600000ms) timeout since builds can take a while.

## Fallback Deploy (No Auth Required)

If the CLI is not installed or fails with "No existing credentials found", use the deploy script:

```bash
skill_dir="/Users/djcavy/Desktop/Trading App/.qoder/skills/vercel-deploy"

# Deploy current directory
bash "$skill_dir/scripts/deploy.sh"

# Deploy specific project
bash "$skill_dir/scripts/deploy.sh" /path/to/project

# Deploy existing tarball
bash "$skill_dir/scripts/deploy.sh" /path/to/project.tgz
```

The script handles framework detection, packaging, and deployment. It waits for the build to complete and returns JSON with `previewUrl` and `claimUrl`.

**Tell the user**: "Your deployment is ready at [previewUrl]. Claim it at [claimUrl] to manage your deployment."

## Production Deploys

Only deploy to production if the user explicitly asks:

```bash
vercel deploy [path] --prod -y
```

## Output

Show the user the deployment URL. For fallback deployments, also show the claim URL.

**Do not curl or fetch the deployed URL** to verify it works. Just return the link.

## Troubleshooting

### Escalated Network Access

If deployment fails due to network issues (timeouts, DNS errors, connection resets), rerun the actual deploy command with escalated permissions. Do not escalate the `command -v vercel` check.

The deploy requires escalated network access when sandbox networking blocks outbound requests.

**Example guidance to the user:**
> The deploy needs escalated network access to deploy to Vercel. I can rerun the command with escalated permissions—want me to proceed?
