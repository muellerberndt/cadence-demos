"""Stage 1 of the robot arm: control on true state before pixels.

The cell is ``arm.world`` unchanged; the teacher is ``arm091.job.smooth_plan``. New here: a
true-state observation (``senses``), Cartesian equilibrium-point actions through a disclosed
IK reflex (``actions``), Cartesian teacher labels (``teacher``), the job assay with the repaired
reach criterion and motion gates (``job``), brains by ``Brain.compose`` (``brains``), the
DAgger-style loop (``train``), the frozen-checkpoint inspection (``inspect``), frame dumps
(``render``) and a torch MLP control (``mlp``).
"""
