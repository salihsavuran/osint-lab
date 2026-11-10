<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api, inferType } from '$lib/api';
  import Graph from '$lib/Graph.svelte';

  let record = $state(null);
  let sources = $state([]);
  let graph = $state({ nodes: [], edges: [], stats: { entities: 0, relations: 0 } });
  let audit = $state([]);
  let tab = $state('entities');
  let reportText = $state('');

  let target = $state('');
  let depth = $state(0);
  let selected = $state([]);
  let busy = $state(false);
  let error = $state('');
  let lastRuns = $state([]);

  const caseId = $derived(Number($page.params.id));
  const inferred = $derived(inferType(target || ''));
  const applicable = $derived(sources.filter((source) => source.accepts.includes(inferred)));

  $effect(() => {
    selected = applicable.map((source) => source.id);
  });

  $effect(() => {
    if (tab === 'report' && !reportText) loadReport();
  });

  async function load() {
    try {
      [record, sources, graph, audit] = await Promise.all([
        api.case(caseId),
        api.sources(),
        api.graph(caseId),
        api.audit(caseId)
      ]);
      error = '';
    } catch (err) {
      error = err.message;
    }
  }

  async function collect() {
    if (!target.trim() || busy) return;
    busy = true;
    error = '';
    try {
      const result = await api.collect(caseId, {
        target: target.trim(),
        collectors: selected,
        depth,
        max_entities: 15
      });
      lastRuns = result.runs;
      await load();
      tab = 'entities';
    } catch (err) {
      error = err.message;
    } finally {
      busy = false;
    }
  }

  async function loadReport() {
    try {
      reportText = await api.report(caseId);
    } catch (err) {
      error = err.message;
    }
  }

  function toggle(id, on) {
    selected = on ? [...new Set([...selected, id])] : selected.filter((value) => value !== id);
  }

  function downloadReport() {
    const blob = new Blob([reportText], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `osint-report-case-${caseId}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  onMount(load);
</script>

{#if error}
  <div class="error">{error}</div>
{/if}

{#if !record}
  <p class="muted">Loading case…</p>
{:else}
  <p class="muted" style="font-size:0.8rem; margin-bottom:0.2rem">
    <a href="/">← all cases</a>
  </p>
  <h1>#{record.id} · {record.title}</h1>
  {#if record.scope_note}
    <p class="muted">Scope: {record.scope_note}</p>
  {/if}

  <section class="panel" style="margin-top:1.25rem">
    <h3>Collect</h3>
    <div class="row" style="margin-top:0.75rem">
      <input
        bind:value={target}
        placeholder="example.com · 8.8.8.8 · https://example.com/ · Organisation name"
        style="flex:1; min-width:280px"
      />
      <label class="muted" style="font-size:0.8rem; display:flex; gap:0.4rem; align-items:center">
        depth
        <select bind:value={depth} style="width:auto">
          <option value={0}>0</option>
          <option value={1}>1</option>
        </select>
      </label>
      <button onclick={collect} disabled={busy || !target.trim() || selected.length === 0}>
        {busy ? 'Collecting…' : 'Collect'}
      </button>
    </div>

    {#if target.trim()}
      <p class="muted" style="font-size:0.82rem; margin-top:0.5rem">
        Detected type: <code>{inferred}</code>
        {#if applicable.length === 0}
          — no collector accepts this type
        {/if}
      </p>
      <div class="checklist">
        {#each applicable as source (source.id)}
          <label>
            <input
              type="checkbox"
              checked={selected.includes(source.id)}
              onchange={(event) => toggle(source.id, event.currentTarget.checked)}
            />
            <span>
              {source.label}
              <span class="meta">{source.id} · {source.rate_limit.requests}/{source.rate_limit.per_seconds}s</span>
            </span>
          </label>
        {/each}
      </div>
    {/if}

    {#if lastRuns.length > 0}
      <table style="margin-top:0.75rem">
        <thead>
          <tr><th>Collector</th><th>Status</th><th>Facts</th><th>Links</th><th>Notes</th></tr>
        </thead>
        <tbody>
          {#each lastRuns as run (run.collector_id)}
            <tr>
              <td><code>{run.collector_id}</code></td>
              <td class:ok={run.status === 'ok'} class:err={run.status === 'error'}>{run.status}</td>
              <td>{run.facts}</td>
              <td>{run.links}</td>
              <td class="muted">{run.error || run.notes.join('; ')}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </section>

  <div class="tabs">
    <button class:active={tab === 'entities'} onclick={() => (tab = 'entities')}>
      Entities ({record.entities.length})
    </button>
    <button class:active={tab === 'graph'} onclick={() => (tab = 'graph')}>
      Graph ({graph.stats.relations})
    </button>
    <button class:active={tab === 'audit'} onclick={() => (tab = 'audit')}>
      Audit log ({audit.length})
    </button>
    <button class:active={tab === 'report'} onclick={() => (tab = 'report')}>Report</button>
    <button class:active={tab === 'sources'} onclick={() => (tab = 'sources')}>Sources</button>
  </div>

  {#if tab === 'entities'}
    {#if record.entities.length === 0}
      <p class="muted">No entities yet. Run a collection above.</p>
    {/if}
    {#each record.entities as entity (entity.id)}
      <article class="entity-card">
        <header>
          <span class="badge {entity.type}">{entity.type}</span>
          <span class="value">{entity.display_name || entity.value}</span>
        </header>
        {#if entity.attributes.length === 0}
          <p class="muted" style="padding:0.8rem 1rem; margin:0; font-size:0.85rem">
            Discovered but not collected.
          </p>
        {:else}
          <table>
            <thead>
              <tr><th>Attribute</th><th>Value</th><th>Source</th><th>Retrieved</th><th>Conf.</th></tr>
            </thead>
            <tbody>
              {#each entity.attributes as attr (attr.key + attr.value)}
                <tr>
                  <td><code>{attr.key}</code></td>
                  <td>{attr.value}</td>
                  <td>
                    {#if attr.url}
                      <a href={attr.url} target="_blank" rel="noreferrer">{attr.source}</a>
                    {:else}
                      {attr.source ?? 'unattributed'}
                    {/if}
                  </td>
                  <td class="muted">{attr.retrieved_at ? new Date(attr.retrieved_at).toLocaleString() : '—'}</td>
                  <td class="muted">{attr.confidence?.toFixed(2) ?? '—'}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </article>
    {/each}
  {:else if tab === 'graph'}
    <Graph {graph} />
  {:else if tab === 'audit'}
    <table>
      <thead>
        <tr><th>When</th><th>Action</th><th>Target</th><th>Detail</th></tr>
      </thead>
      <tbody>
        {#each audit as event (event.id)}
          <tr>
            <td class="muted">{new Date(event.created_at).toLocaleString()}</td>
            <td><code>{event.action}</code></td>
            <td>{event.target}</td>
            <td class="muted" style="font-size:0.8rem">{event.detail}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {:else if tab === 'report'}
    <div class="row" style="margin-bottom:0.75rem">
      <button class="secondary" onclick={loadReport}>Refresh</button>
      <button class="secondary" onclick={downloadReport} disabled={!reportText}>
        Download .md
      </button>
    </div>
    {#if reportText}
      <pre class="report">{reportText}</pre>
    {:else}
      <p class="muted">Generating…</p>
    {/if}
  {:else if tab === 'sources'}
    {#each sources as source (source.id)}
      <article class="entity-card">
        <header>
          <code>{source.id}</code>
          <strong>{source.label}</strong>
          <span class="muted" style="margin-left:auto; font-size:0.78rem">
            {source.rate_limit.requests} req / {source.rate_limit.per_seconds}s
          </span>
        </header>
        <div style="padding:0.8rem 1rem">
          <p style="margin:0 0 0.4rem">{source.description}</p>
          <p class="muted" style="margin:0; font-size:0.82rem">
            <strong>Legal basis:</strong> {source.legal_basis}
          </p>
        </div>
      </article>
    {/each}
  {/if}
{/if}
