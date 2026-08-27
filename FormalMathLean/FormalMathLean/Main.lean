import Mathlib

example (x : ℝ) : 0 ≤ x ^ 2 := by
  positivity

example (x : ℝ) (h : x ^ 2 = x) : x = 0 ∨ x = 1 := by
  have hfactor : x * (x - 1) = 0 := by
    nlinarith [h]
  rcases mul_eq_zero.mp hfactor with hx | hx
  · exact Or.inl hx
  · right
    linarith