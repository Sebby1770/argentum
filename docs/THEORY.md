# Argentum — formula sheet

Short, sourced identities. Implementers should treat this file as the
spec; the code is the executable version.

## 1. Black–Scholes–Merton

With forward \(F = S e^{(r-q)T}\), \(\tau = \sigma\sqrt{T}\):

\[
d_1 = \frac{\ln(F/K) + \tfrac12\sigma^2 T}{\tau},\quad
d_2 = d_1 - \tau
\]

\[
C = e^{-rT}\bigl(F\,N(d_1) - K\,N(d_2)\bigr),\quad
P = e^{-rT}\bigl(K\,N(-d_2) - F\,N(-d_1)\bigr)
\]

Greeks (spot measure): \(\Delta = e^{-qT}N(d_1)\),
\(\Gamma = e^{-qT}n(d_1)/(S\sigma\sqrt{T})\),
\(\nu = S e^{-qT} n(d_1)\sqrt{T}\) (per 1.0 of vol),
\(\rho = K T e^{-rT} N(d_2)\).
Charm, vanna, volga, speed, zomma, color follow Haug.

Implied vol: Halley on \(C(\sigma)-C^\star\) with analytic vega and volga,
Brenner–Subrahmanyam seed, Brent fallback. Domain: intrinsic \(\le C \le S e^{-qT}\).

## 2. Black (1976) and Bachelier

Black is BSM on a forward. Bachelier (normal):

\[
C = e^{-rT}\Bigl[(F-K)N(d) + \sigma_n\sqrt{T}\,n(d)\Bigr],\quad
d = (F-K)/(\sigma_n\sqrt{T})
\]

## 3. SABR (Hagan et al., Wilmott 2002)

CEV backbone \(dF = \alpha F^\beta dW^1\), \(d\alpha = \nu\alpha\,dW^2\),
\(\langle dW^1,dW^2\rangle=\rho\,dt\). Lognormal implied vol as implemented
in `models/sabr.py` (ATM and \(F\neq K\) branches, including the \(z/x(z)\)
term). Shifted SABR is the same formula on \((F+s, K+s)\).

## 4. Raw SVI (Gatheral)

\[
w(k) = a + b\bigl(\rho(k-m) + \sqrt{(k-m)^2+\sigma^2}\bigr)
\]

No butterfly arb \(\Leftrightarrow g(k)\ge 0\) (Gatheral–Jacquier). Calendar
arb is \(\partial_T w \ge 0\), checked by the caller across slices.

## 5. Heston COS (Fang–Oosterlee 2008)

Little-Heston-trap CF (Albrecher et al.) so \(\log\) stays principal-valued.
Truncation \([c_1 - L\sqrt{c_2},\, c_1 + L\sqrt{c_2}]\) from the first two
cumulants of \(\log S_T\). Put coefficients via \(\chi_k, \psi_k\); call by
parity.

## 6. Day counts (ISDA 2006)

- Act/365F: \(\Delta t / 365\)
- Act/360: \(\Delta t / 360\)
- Act/Act ISDA: split at year boundaries; each stub over 365 or 366
- 30U/360: D1=31→30; D2=31→30 iff D1≥30; both last-of-Feb → 30
- 30E/360: both days min(d, 30)
- 30E/360 ISDA: last of month → 30 except Feb termination on D2

## 7. Dual-curve swap

Forecast \(L(t_i, t_{i+1}) = \bigl(P_{\text{fwd}}(t_i)/P_{\text{fwd}}(t_{i+1}) - 1\bigr)/\delta_i\).
Discount with \(P_{\text{ois}}\). Par rate \(S = \text{PV}_{\text{float}} / A\).

## 8. CDS

Protection \(\approx (1-R)\sum \bigl(S(t_i)-S(t_{i+1})\bigr) P(t_{i+1/2})\).
Premium = coupon × risky annuity (survival-weighted \(\delta_i P(t_i)\), plus
half-accrual on default). Par spread = protection / annuity.

## 9. Hull–White 1F ZBO

\(B(t,T)=(1-e^{-a(T-t)})/a\). Bond-option vol
\(\Sigma = B(T_e,T_b)\sigma\sqrt{(1-e^{-2a T_e})/(2a)}\). Black formula on
\(P(0,T_b)\) vs \(K\,P(0,T_e)\).

## 10. Interpolation

Default curve interpolator: **linear on log DF** (piecewise-constant
instantaneous forward). Optional natural cubic and Hyman (1983) monotone
cubic on the same coordinate.
