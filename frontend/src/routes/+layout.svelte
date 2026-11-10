<script>
  import '../app.css';
  let { children } = $props();
</script>

<header class="topbar">
  <a class="brand" href="/">osint<span>·</span>lab</a>
  <span class="tag">educational</span>
  <span class="muted" style="margin-left:auto; font-size:0.8rem">
    every fact is attributed
  </span>
</header>

<main>
  {@render children()}
</main>
