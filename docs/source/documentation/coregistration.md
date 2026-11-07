# Head-to-MRI coregistration

Use **BIDS > Coregistration...** to align EEG, MEG, or iEEG recordings with
their FreeSurfer MRI reconstructions.

## Before you start

You need a BIDS dataset with digitization and fiducials, plus a matching
FreeSurfer reconstruction with a suitable head surface and MRI information.
See [subjects](subjects.md) to select or import reconstructions.

## Fit and inspect

1. Open **BIDS > Coregistration...** and select a digitization group.
   Recordings are grouped only when their digitization matches within the
   same subject and session.
2. Choose the correct **FreeSurfer subject**. Verify that it belongs to the
   participant, even if it is selected automatically.
3. Run **Automatic coregistration**, or open **Manual coregistration / inspect**
   to fit manually.
4. Inspect the alignment in the manual window, even after automatic fitting.
   Adjust it if needed and choose **Save to derivatives**.

![Coregistration manager with two example recordings.](../_static/screenshots/linux/coregistration.png)

Select a digitization group and its matching MRI subject.

Check marks indicate that transformations exist, **not** that alignment is
correct. The example uses synthetic metadata, not an anatomical fit.

## Reuse and save

To apply an existing transformation to matching recordings, select the
recording with the transformation and choose **Reuse selected transformation
for group**. Saving creates recording-specific transformation files in the
configured [derivative folder](derivatives.md) and asks before replacing
existing files.

If existing transformations are ambiguous, resolve the conflict or save the
intended transformation in the configured derivatives folder.
