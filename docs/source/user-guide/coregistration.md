# Coregistration

Coregistration aligns the head position of a recording with the MRI of the
participant. The result is the transformation behind the `trans` port of the
input node.

You need digitized head points with fiducials in the BIDS dataset and a
[FreeSurfer reconstruction](freesurfer.md) of the participant.

## Fit and inspect

Open **BIDS > Coregistration...**.

![The coregistration dialog with a digitization group and its recordings](../_static/screenshots/linux/coregistration.png)

1. Select a group. Recordings of one subject and session with identical
   digitization share a group.
2. Choose the **FreeSurfer subject**. Check that it really is this
   participant, even if it was selected automatically.
3. Click **Automatic coregistration**, or fit by hand with **Manual
   coregistration / inspect**.
4. Always inspect the alignment in the manual window, then choose **Save to
   derivatives**.

!!! warning
    A check mark means that a transformation exists, not that it is correct.

## Reuse a transformation

Select the recording that has a transformation and click **Reuse selected
transformation for group** to apply it to the other recordings of the group.

Transformations are saved per recording in the
[results folder](derivatives.md). You are asked before a file is replaced.
