---
name: netlify-deploy
description: Deploy web projects to Netlify using the Netlify CLI with intelligent detection of project configuration and deployment context. Use when the user wants to deploy a project to Netlify, create a preview deployment, or set up Netlify hosting for a web project.
---

# Netlify Deployment

Deploy web projects to Netlify using the Netlify CLI with intelligent detection of project configuration and deployment context.

## Prerequisites

- Netlify CLI: Installed via npx (no global install required)
- Authentication: Netlify account with active login session
- Project: Valid web project in current directory

## Workflow

### 1. Verify Netlify CLI Authentication

Check if the user is logged into Netlify:

```bash
npx netlify status
```

Expected output patterns:
- **Authenticated**: Shows logged-in user email and site link status
- **Not authenticated**: "Not logged into any site" or authentication error

If not authenticated, guide the user:

```bash
npx netlify login
```

This opens a browser window for OAuth authentication. Wait for user to complete login, then verify with `netlify status` again.

**Alternative: API Key authentication**

If browser authentication isn't available, users can set:

```bash
export NETLIFY_AUTH_TOKEN=your_token_here
```

Tokens can be generated at: https://app.netlify.com/user/applications#personal-access-tokens

### 2. Detect Site Link Status

From `netlify status` output, determine:
- **Linked**: Site already connected to Netlify (shows site name/URL)
- **Not linked**: Need to link or create site

### 3. Link to Existing Site or Create New

If already linked → Skip to step 4

If not linked, attempt to link by Git remote:

```bash
# Check if project is Git-based
git remote show origin

# Try to link by Git remote
npx netlify link --git-remote-url <REMOTE_URL>
```

If link fails (site doesn't exist on Netlify):

```bash
# Create new site interactively
npx netlify init
```

This guides user through:
- Choosing team/account
- Setting site name
- Configuring build settings
- Creating netlify.toml if needed

### 4. Verify Dependencies

Before deploying, ensure project dependencies are installed:

```bash
npm install
```

For other package managers, detect and use appropriate command (yarn install, pnpm install, etc.)

### 5. Deploy to Netlify

Choose deployment type based on context:

**Preview/Draft Deploy** (default for existing sites):

```bash
npx netlify deploy
```

This creates a deploy preview with a unique URL for testing.

**Production Deploy** (for new sites or explicit production deployments):

```bash
npx netlify deploy --prod
```

This deploys to the live production URL.

### 6. Report Results

After deployment, report to user:
- **Deploy URL**: Unique URL for this deployment
- **Site URL**: Production URL (if production deploy)
- **Deploy logs**: Link to Netlify dashboard for logs
- **Next steps**: Suggest `netlify open` to view site or dashboard

## Handling netlify.toml

If a netlify.toml file exists, the CLI uses it automatically. If not, the CLI will prompt for:
- **Build command**: e.g., `npm run build`, `next build`
- **Publish directory**: e.g., `dist`, `build`, `.next`

Common framework defaults:
- **Next.js**: build command `npm run build`, publish `.next`
- **React (Vite)**: build command `npm run build`, publish `dist`
- **Static HTML**: no build command, publish current directory

Detect framework from package.json if possible and suggest appropriate settings.

## Error Handling

Common issues and solutions:

| Error | Solution |
|-------|----------|
| "Not logged in" | Run `npx netlify login` |
| "No site linked" | Run `npx netlify link` or `npx netlify init` |
| "Build failed" | Check build command and publish directory in netlify.toml or CLI prompts. Verify dependencies are installed. Review build logs for specific errors. |
| "Publish directory not found" | Verify build command ran successfully. Check publish directory path is correct. |

## Troubleshooting

### Escalated Network Access

If deployment fails due to network issues (timeouts, DNS errors, connection resets), rerun the deploy with escalated permissions. The deploy requires escalated network access when sandbox networking blocks outbound requests.

Ask the user: "The deploy needs escalated network access to deploy to Netlify. I can rerun the command with escalated permissions—want me to proceed?"

### Environment Variables

For secrets and configuration:
- Never commit secrets to Git
- Set in Netlify dashboard: Site Settings → Environment Variables
- Access in builds via `process.env.VARIABLE_NAME`

## Tips

- Use `netlify deploy` (no --prod) first to test before production
- Run `netlify open` to view site in Netlify dashboard
- Run `netlify logs` to view function logs (if using Netlify Functions)
- Use `netlify dev` for local development with Netlify Functions

## References

- Netlify CLI Docs: https://docs.netlify.com/cli/get-started/
- netlify.toml Reference: https://docs.netlify.com/configure-builds/file-based-configuration/
