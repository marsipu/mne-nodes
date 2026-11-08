# Implementation notes

For core services, state ownership, and widgets, see [architecture](architecture.md),
[configuration](configuration.md), and [widgets](widgets.md). These notes cover specialized
invariants used by configuration generation, execution, and styling.

## MNE port aliases

`development/_generate_mne_config.py` derives accepted port names from MNE
class names and documented parameter names. Add naming mismatches that cannot
be inferred from classes to `hard_aliases`, listing both directions (for
example, `surfs` and `surfaces`). These aliases are included for inputs,
outputs and I/O matching. A matching container parameter is treated as a node
input, but primitive parameters such as booleans remain editable parameters.
Regenerate the plugin configs to apply alias changes to the application.

## Subject-only execution

The code generator tracks subject-only values separately from loaded values.
Loading `subject` from a recording starts that dependency chain. A non-method
node with outputs joins the chain only when all its supplied inputs are
subject-only; its outputs then propagate that property. Disk-loaded derivatives
are not assumed to be subject-only. Recording inputs such as `info` or
`trans` break the chain.
Passing an object to a non-shared node also ends its subject-only provenance:
that node may modify it in place. Other live objects may alias the mutated
inputs, so their provenance is conservatively cleared too. The immutable
resolved subject name is exempt.

Generated scripts keep a run-local cache keyed by execution target, node name
and resolved FreeSurfer subject. Distinct nodes therefore keep their own
parameters, while different recordings or groups using the same reconstruction
reuse a node's result. Outputs and live subject-only values are deep-copied
together so cache hits restore in-place changes and aliases made by the shared
node, while downstream changes cannot mutate the cache.
Saving stays outside the computation cache,
preserving the current derivative I/O behavior. No persistent cache is added.

## Semantic colors

`mne_nodes.gui.colors` is the application-wide registry for semantic colors.
`CATEGORY_COLORS` stores the MNE-logo-derived HEX palette, and
`CATEGORY_DATATYPES` assigns known datatype names and aliases to categories.
`DATATYPE_CATEGORIES` is derived from those assignments. Add new type names to
the category membership rather than duplicating colors in individual widgets.

Use `datatype_color(name, accepted_datatypes)` to resolve a color. An explicit
known name wins; otherwise accepted aliases must agree on one category.
Unknown or mixed-category outputs retain the consumer's default styling.
Output ports and input-node datatype tabs use this API; future node and parameter
coloring should reuse it. Larger widgets should use restrained accents rather
than saturated backgrounds. `ACCENT_OPACITY` and `ACTIVE_ACCENT_OPACITY` in
the same registry control the translucent tab underlines. The active page frame
uses `ACCENT_OPACITY` for a matching border; native labels and backgrounds are
preserved. Normal, connected and hovered outputs retain their
semantic color.
Disabled outputs are dimmed, while temporary connection-compatibility highlights
keep their existing meaning.
