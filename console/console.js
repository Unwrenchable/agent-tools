(function () {
  const runBtn = document.getElementById('runBtn');
  const out = document.getElementById('output');

  function buildCommand() {
    const agent = document.getElementById('agent').value.trim();
    const provider = document.getElementById('provider').value.trim();
    const input = document.getElementById('input').value.trim().replace(/"/g, '\\"');
    const dryRun = document.getElementById('dry').checked;

    const args = ['agent-tools run', agent, '--input', `"${input}"`, '--json'];
    if (provider) args.push('--provider', provider);
    if (dryRun) args.push('--dry-run');
    return args.join(' ');
  }

  runBtn.addEventListener('click', () => {
    out.textContent = [
      buildCommand(),
      '',
      'Run the command in your terminal to inspect JSON logs, latency, tool calls, and output.'
    ].join('\n');
  });
})();
