<script>
  import cytoscape from 'cytoscape';

  let { graph } = $props();
  let container = $state();
  let cy = null;

  const palette = {
    domain: '#4C8BF5',
    ip: '#34A853',
    prefix: '#FBBC05',
    asn: '#EA4335',
    url: '#9AA0A6',
    organization: '#A142F4',
    sanctions: '#D93025'
  };

  $effect(() => {
    if (!container) return;

    if (!cy) {
      cy = cytoscape({
        container,
        elements: [],
        wheelSensitivity: 0.2,
        style: [
          {
            selector: 'node',
            style: {
              label: 'data(label)',
              'font-size': 10,
              color: '#e6e9ef',
              'text-valign': 'bottom',
              'text-margin-y': 5,
              'background-color': 'data(color)',
              width: 14,
              height: 14
            }
          },
          {
            selector: 'node:selected',
            style: { 'border-width': 2, 'border-color': '#fff' }
          },
          {
            selector: 'edge',
            style: {
              width: 1,
              'line-color': '#3a4150',
              'target-arrow-color': '#3a4150',
              'target-arrow-shape': 'triangle',
              'curve-style': 'bezier',
              'arrow-scale': 0.7
            }
          }
        ]
      });
    }

    const elements = [
      ...graph.nodes.map((node) => ({
        data: {
          id: String(node.id),
          label: node.label,
          color: palette[node.type] || '#9AA0A6'
        }
      })),
      ...graph.edges.map((edge) => ({
        data: {
          id: `e${edge.id}`,
          source: String(edge.source),
          target: String(edge.target)
        }
      }))
    ];

    cy.elements().remove();
    cy.add(elements);
    cy.layout({ name: 'cose', animate: false, padding: 40, nodeRepulsion: 9000 }).run();
  });
</script>

{#if graph.nodes.length === 0}
  <p class="muted">Nothing to draw yet — collect against the target first.</p>
{:else}
  <div bind:this={container} class="graph"></div>
  <p class="muted" style="font-size:0.8rem; margin-top:0.5rem">
    {graph.stats.entities} entities · {graph.stats.relations} relations ·
    drag to reposition, scroll to zoom
  </p>
{/if}
