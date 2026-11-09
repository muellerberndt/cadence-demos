"""Connect Four on Cadence: a policy brain taught by a perfect solver.

``game`` holds the rules, ``solver`` Pascal Pons' solver as the teacher and the grader,
``positions`` the position sources, ``gen_pool`` a shared pool of solver-labelled positions,
``policy`` the Cadence brain and its MLP control, ``evaluate`` the readings during training,
``train`` the teaching loop, ``reading`` the readings of a saved brain and ``page_copy`` the
brain the page loads.
"""
