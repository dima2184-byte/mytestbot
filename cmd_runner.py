import json, os, subprocess, time, urllib.request, urllib.error
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH_USER  = os.environ.get("GH_USER", "dima2184-byte")
REPO     = os.environ.get("REPO_NAME", "mytestbot")
BRANCH   = "main"
API      = f"https://api.github.com/repos/{GH_USER}/{REPO}/contents"
HEADERS  = {
    "Authorization": f"token {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
POLL_SEC   = 5
CMD_TIMEOUT = 120
MAX_OUT    = 3000

last_id = None


def gh_get(path: str) -> dict:
    req = urllib.request.Request(f"{API}/{path}?ref={BRANCH}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def gh_put(path: str, content: str, sha: str) -> None:
    import base64
    body = json.dumps({
        "message": f"cmd_runner: update {path}",
        "content": base64.b64encode(content.encode()).decode(),
        "sha": sha,
        "branch": BRANCH,
    }).encode()
    req = urllib.request.Request(
        f"{API}/{path}", data=body, headers={**HEADERS, "Content-Type": "application/json"},
        method="PUT"
    )
    with urllib.request.urlopen(req, timeout=15):
        pass


def read_json_file(path: str) -> tuple[dict, str]:
    """Returns (parsed_json, sha)."""
    import base64
    data = gh_get(path)
    content = base64.b64decode(data["content"]).decode()
    return json.loads(content), data["sha"]


def run_cmd(cmd: str) -> dict:
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=CMD_TIMEOUT
        )
        stdout = result.stdout[-MAX_OUT:] if len(result.stdout) > MAX_OUT else result.stdout
        return {
            "stdout": stdout,
            "stderr": result.stderr[-1000:],
            "returncode": result.returncode,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "timeout", "returncode": -1,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def main():
    global last_id
    print("cmd_runner started", flush=True)
    while True:
        try:
            pending, _ = read_json_file("cmds/pending.json")
            cmd_id = pending.get("id")
            if cmd_id and cmd_id != last_id:
                print(f"Running command id={cmd_id}: {pending['cmd']}", flush=True)
                output = run_cmd(pending["cmd"])
                output["id"] = cmd_id
                _, result_sha = read_json_file("cmds/result.json")
                gh_put("cmds/result.json", json.dumps(output, ensure_ascii=False, indent=2), result_sha)
                last_id = cmd_id
                print(f"Done id={cmd_id} rc={output['returncode']}", flush=True)
        except Exception as e:
            print(f"cmd_runner error: {e}", flush=True)
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
