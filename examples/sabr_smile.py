"""Print a SABR lognormal smile around a 3% forward."""

from argentum.models.sabr import sabr_implied_vol

F, T, alpha, beta, rho, nu = 0.03, 5.0, 0.04, 0.5, -0.3, 0.5
print(f"{'K':>8} {'vol':>10}")
for k_bp in range(50, 551, 25):
    k = k_bp / 10_000.0
    vol = sabr_implied_vol(F, k, T, alpha, beta, rho, nu)
    print(f"{k:8.4f} {vol:10.4%}")
