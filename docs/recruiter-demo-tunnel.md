# Run the FrameFlux recruiter demo through your computer

This setup runs the Backend demo branch on your Windows computer and temporarily exposes only its local API port through a Cloudflare Quick Tunnel. The frontend remains separately hosted from the Frontend demo branch. Neither repository main branch is involved.

## What this setup does

- Starts app.demo.main:app from this repository's demo branch on 127.0.0.1:8000.
- Checks the API's /demo/runtime health endpoint before opening the tunnel.
- Restricts browser CORS to the frontend origin you provide.
- Starts a temporary trycloudflare.com HTTPS URL.
- Shuts down the local API when you stop the tunnel with Ctrl+C.

The backend is an in-memory recruiter simulation. It does not run FFmpeg, PostgreSQL, Redis, or ARQ workers. Processed media responses are placeholders, and the server's shared demo state resets when the process stops.

## One-time prerequisites (Windows)

1. Install Python 3.10 or newer.
2. Install cloudflared:

       winget install --id Cloudflare.cloudflared --exact

3. Open a new PowerShell window and confirm python --version and cloudflared --version work.

Cloudflare Quick Tunnels do not require a Cloudflare account or custom domain. Their hostname is random and changes when a new tunnel is started.

## Start the API and tunnel

From the root of your local clone of FrameFlux-Backend, make sure you have checked out the demo branch, pulled its latest changes, and run:

    .\scripts\start-recruiter-demo-tunnel.ps1 -FrontendOrigin "https://frame-flux-demo-git-demo-focus-journals-projects.vercel.app"

Use only the frontend demo site's origin: include https://, but no route or trailing path. The script creates .venv if needed, installs only the standalone demo API dependencies, starts Uvicorn on loopback, checks its health, and then launches cloudflared.

The terminal prints a random URL similar to:

    https://random-words.trycloudflare.com

Keep the PowerShell window open while recruiters use the demo. Press Ctrl+C in that window to stop the tunnel and API.

## Connect the hosted frontend

Copy the random tunnel URL and URL-encode it. Then open:

    https://frame-flux-demo-git-demo-focus-journals-projects.vercel.app/?demoBackend=https%3A%2F%2Frandom-words.trycloudflare.com

The frontend demo branch recognizes the demoBackend query parameter, stores the URL for the current browser tab session, and removes the parameter from the address bar. You can share that complete link with a recruiter. The frontend validates that query-supplied backend URLs use HTTPS and the trycloudflare.com hostname.

When the tunnel URL changes, create a new frontend link using the new URL. To switch the current tab back to browser-only simulation, open:

    https://frame-flux-demo-git-demo-focus-journals-projects.vercel.app/?demoBackend=local

If the tunnel is offline or unreachable, the frontend falls back to its browser-local simulation. That fallback is intentional; do not mistake it for a successful connection to the backend. The tunnel URL must be active before a recruiter opens the linked frontend.

## Important safety and demo limitations

- A Quick Tunnel is temporary, intended for testing, and has no uptime guarantee. The random public URL stops working after the tunnel process stops.
- Anyone who obtains the random URL can call the demo API. Treat the URL like a temporary access link, share it only with intended testers, and stop the tunnel after the session. CORS limits browser origins; it is not API authentication.
- Do not add Cloudflare's `--allowed-mail` gate to this API tunnel without redesigning and testing the browser authentication flow. The frontend sends credentialed, preflighted cross-origin API requests; Cloudflare Access requires a valid authorization cookie, and its documentation states that protected preflight `OPTIONS` requests are blocked unless separately bypassed/configured. The Quick Tunnel launcher does not configure that bypass.
- The backend currently uses one in-memory demo workspace shared by requests reaching that running process. Do not run concurrent recruiter sessions against the same tunnel if they need isolated data.
- Do not upload confidential or personal media. The API is a simulation and does not provide production storage or actual transcoding.
- The API binds to 127.0.0.1, not 0.0.0.0; the tunnel is the only intended remote entry point.

For a stable recruiter demo or concurrent isolated sessions, use a separately secured hosted demo backend rather than a local Quick Tunnel.
