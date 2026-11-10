<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api';

  let cases = $state([]);
  let error = $state('');
  let loading = $state(true);
  let busy = $state(false);
  let title = $state('');
  let scope = $state('');

  async function load() {
    loading = true;
    try {
      cases = await api.cases();
      error = '';
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }

  async function create() {
    if (!title.trim() || busy) return;
    busy = true;
    try {
      const created = await api.createCase(title.trim(), scope.trim());
      cases = [created, ...cases];
      title = '';
      scope = '';
      error = '';
    } catch (err) {
      error = err.message;
    } finally {
      busy = false;
    }
  }

  onMount(load);
</script>

<h1>Cases</h1>
<p class="muted">
  A case is a container for one investigation. Record why the target is in scope
  before you collect — it goes into the audit log and the report.
</p>

{#if error}
  <div class="error">{error}</div>
{/if}

<section class="panel" style="margin-top:1.25rem">
  <h3>New case</h3>
  <div class="grid" style="margin-top:0.75rem; grid-template-columns: 1fr 2fr auto; align-items:end">
    <label>
      <span class="muted" style="font-size:0.8rem">Title</span>
      <input bind:value={title} placeholder="e.g. Infrastructure review: example.com" />
    </label>
    <label>
      <span class="muted" style="font-size:0.8rem">Scope note</span>
      <input bind:value={scope} placeholder="Why is this target legitimate and in scope?" />
    </label>
    <button onclick={create} disabled={busy || !title.trim()}>
      {busy ? 'Creating…' : 'Create'}
    </button>
  </div>
</section>

<h2>Your cases</h2>

{#if loading}
  <p class="muted">Loading…</p>
{:else if cases.length === 0}
  <p class="muted">No cases yet. Create one above to get started.</p>
{:else}
  <div class="grid case-list">
    {#each cases as item (item.id)}
      <a href={`/cases/${item.id}`}>
        <div class="row" style="justify-content:space-between">
          <strong>#{item.id} · {item.title}</strong>
          <span class="muted" style="font-size:0.8rem">
            {item.entity_count} entities · {new Date(item.created_at).toLocaleString()}
          </span>
        </div>
        {#if item.scope_note}
          <div class="muted" style="font-size:0.85rem; margin-top:0.2rem">
            {item.scope_note}
          </div>
        {/if}
      </a>
    {/each}
  </div>
{/if}
