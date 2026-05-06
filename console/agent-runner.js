export function buildRunnerCommand({ agentId, input, provider, dryRun }) {
  const escaped = String(input).replace(/"/g, '\\"');
  const command = ['agent-tools run', agentId, '--input', `"${escaped}"`, '--json'];
  if (provider) command.push('--provider', provider);
  if (dryRun) command.push('--dry-run');
  return command.join(' ');
}
