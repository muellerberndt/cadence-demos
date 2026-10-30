"""Stage 2 of the robot arm: the same job under contact physics.

A Franka Panda with its gripper (MuJoCo Menagerie, vendored under ``menagerie/`` with its
license and source commit) in plain MuJoCo on the CPU: physics at the model's 500 Hz, one
decision every 100 steps (0.2 s, the cell's 12-frame decision), the joint position actuators as
equilibrium points. The table, one block of random size, mass and friction, two bins and the lit
lamp follow ``arm.world``; grasp, lift and place are read from contacts and the block's height.
The observation, the Cartesian action slots through the IK reflex, the teacher's continuous
waypoints, the DAgger-style loop and the frozen inspection follow ``arm1``.
"""
