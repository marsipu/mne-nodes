# FreeSurfer plugin execution

## Python functions

Set `uses_freesurfer` to `true` for a plugin function that must run in a
FreeSurfer environment. The importer exposes this as **Run in FreeSurfer
environment**. Use importable module-level callables, not closures or instance
methods. Arguments and results cross a subprocess boundary through temporary
pickle files: do not pass Qt objects or rely on in-place input mutation.

On Windows, execution uses WSL; otherwise it runs natively. Path values are
translated for the receiving system. MNE-Nodes sets `SUBJECTS_DIR` for its
own process and children to the active dataset's configured subjects directory;
it does not change the parent shell or MNE's saved configuration.

## Command nodes

Define `command` as an argument list and `command_args` as a mapping from
input/parameter names to flags. `true` adds a flag, `false` and `null`
omit it, lists repeat the flag, and a null flag passes positional arguments.
Arguments remain separate tokens; shell substitutions and redirections are not
evaluated. Command outputs pass through matching supplied arguments.

`bids_subject_from` names the anatomical image argument from which a
`sub-<label>` subject is derived. Use it instead of an explicit subject.
See the FreeSurfer plugin for complete metadata examples.

## Tests

The regular suite uses synthetic subprocesses and does not require FreeSurfer.
`MNENODES_TEST_FREESURFER=1` enables optional integration tests on a machine
with FreeSurfer and a license; these test watershed on a temporary MRI copy.
