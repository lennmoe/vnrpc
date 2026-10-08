export const REPO = "https://github.com/lennmoe/vnrpc";
export const RELEASES_PAGE = `${REPO}/releases`;

export const DISCORD_INVITE = "https://discord.gg/2SUrBSYzbK";

function windowsVersion() {
  return /Windows NT 10/.test(navigator.userAgent) ? "Windows 10/11" : "Windows";
}

function issueUrl({ title, body, label }) {
  const params = new URLSearchParams({ title, body, labels: label });
  return `${REPO}/issues/new?${params}`;
}

export function bugReportUrl(version) {
  const body = [
    "**What happened?**",
    "",
    "",
    "**What did you expect?**",
    "",
    "",
    "**How to make it happen again** (the VN, what you clicked…)",
    "",
    "",
    "---",
    `Visual Novel RPC ${version} · ${windowsVersion()}`,
  ].join("\n");

  return issueUrl({ title: "Bug: ", body, label: "bug" });
}

export function suggestionUrl(version) {
  const body = [
    "**What would you like?**",
    "",
    "",
    "**Why / when would it help?**",
    "",
    "",
    "---",
    `Visual Novel RPC ${version}`,
  ].join("\n");

  return issueUrl({ title: "Idea: ", body, label: "enhancement" });
}
