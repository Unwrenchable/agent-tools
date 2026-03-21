# Quantitative Methods - Formula Reference

This knowledge page provides a comprehensive reference for quantitative methods formulas, based on the CFA Level 1 Quantitative Methods curriculum. The formulas are organized by topic for quick reference.

**Source**: [300Hours CFA Level 1 Quantitative Methods Cheat Sheet](https://300hours.com/cfa-level-1-quantitative-methods-cheat-sheet/)

---

## 1. Time Value of Money

### Future Value (FV)
```
FV = PV × (1 + r)^n
```
Where:
- PV = Present Value
- r = interest rate per period
- n = number of periods

### Present Value (PV)
```
PV = FV / (1 + r)^n
```

### Annuity - Present Value (Ordinary Annuity)
```
PV = A × [(1 - (1 + r)^-n) / r]
```
Where:
- A = periodic payment amount
- r = interest rate per period
- n = number of periods

### Annuity - Future Value
```
FV = A × [((1 + r)^n - 1) / r]
```

### Perpetuity Present Value
```
PV = A / r
```
A perpetuity is an infinite series of equal payments.

### Effective Annual Rate (EAR)
```
EAR = (1 + r_nom/m)^m - 1
```
Where:
- r_nom = nominal annual rate
- m = number of compounding periods per year

### EAR with Continuous Compounding
```
EAR = e^r - 1
```
Where e is Euler's number (≈2.71828)

---

## 2. Rates of Return

### Holding Period Return (HPR)
```
HPR = (P_end - P_begin + Income) / P_begin
```
Where:
- P_end = ending price
- P_begin = beginning price
- Income = dividends or interest received

### Arithmetic Mean
```
x̄ = Σx_i / n
```
The simple average of a set of values.

### Geometric Mean
```
GM = [(1 + R_1) × (1 + R_2) × ... × (1 + R_n)]^(1/n) - 1
```
Used for calculating average compound returns over multiple periods.

---

## 3. Statistical Measures

### Population Variance
```
σ² = Σ(x_i - μ)² / N
```
Where:
- μ = population mean
- N = population size

### Sample Variance
```
s² = Σ(x_i - x̄)² / (n - 1)
```
Note: Uses (n-1) for degrees of freedom (Bessel's correction).

### Standard Deviation
```
σ = √(σ²)
```
The square root of variance.

### Coefficient of Variation (CV)
```
CV = σ / x̄
```
Measures relative variability (standard deviation per unit of mean).

---

## 4. Probability

### Conditional Probability
```
P(A|B) = P(AB) / P(B)
```
The probability of A given that B has occurred.

### Joint Probability (Independent Events)
```
P(AB) = P(A) × P(B)
```
Only valid when A and B are independent.

### Bayes' Theorem
```
P(Event|Info) = [P(Info|Event) × P(Event)] / P(Info)
```
Used to update probabilities based on new information.

---

## 5. Portfolio Mathematics

### Variance of a Two-Asset Portfolio
```
σ²_p = w₁²σ₁² + w₂²σ₂² + 2w₁w₂ρ₁₂σ₁σ₂
```
Where:
- w₁, w₂ = portfolio weights of assets 1 and 2
- σ₁, σ₂ = standard deviations of assets 1 and 2
- ρ₁₂ = correlation coefficient between assets 1 and 2

### Covariance
```
Cov(X, Y) = Σ[p(x,y) × (x - E(X)) × (y - E(Y))]
```
Measures how two variables move together.

### Correlation Coefficient
```
ρ_XY = Cov(X, Y) / (σ_X × σ_Y)
```
Normalized covariance ranging from -1 to +1.

---

## 6. Sampling & Estimation

### Confidence Interval (Known Variance)
```
x̄ ± z_(α/2) × (σ / √n)
```
Where:
- x̄ = sample mean
- z_(α/2) = critical z-value for desired confidence level
- σ = population standard deviation
- n = sample size

### Confidence Interval (Sample Standard Deviation)
```
x̄ ± t_(α/2, n-1) × (s / √n)
```
Where:
- t_(α/2, n-1) = critical t-value with (n-1) degrees of freedom
- s = sample standard deviation

### Central Limit Theorem
As sample size increases, the distribution of sample means approaches a normal distribution, regardless of the underlying population distribution. This is valid for large samples (typically n ≥ 30).

---

## 7. Hypothesis Testing

### Test Statistic (Z-test for Means)
```
z = (x̄ - μ) / (σ / √n)
```
Used when population variance is known or sample size is large.

### Test Statistic (T-test for Means)
```
t = (x̄ - μ) / (s / √n)
```
Used when population variance is unknown and sample size is small.

### Type I and Type II Errors

- **Type I Error (α)**: False positive - Rejecting a true null hypothesis
  - α is the significance level (commonly 0.05 or 0.01)

- **Type II Error (β)**: False negative - Failing to reject a false null hypothesis
  - Power of test = 1 - β

---

## 8. Regression Analysis

### Simple Linear Regression Model
```
ŷ = a + bx
```
Where:
- ŷ = predicted value of dependent variable
- a = y-intercept
- b = slope coefficient
- x = independent variable

### Slope Coefficient
```
b = Cov(X,Y) / Var(X)
```
Or equivalently:
```
b = ρ_XY × (σ_Y / σ_X)
```

### Y-Intercept
```
a = ȳ - b × x̄
```
Where ȳ and x̄ are the means of Y and X respectively.

### Coefficient of Determination (R²)
```
R² = (Explained Variation) / (Total Variation)
```
Represents the proportion of variance in Y explained by X. Ranges from 0 to 1.

---

## Quick Reference Tables

### When to Use Z-test vs T-test

| Condition | Test to Use |
|-----------|-------------|
| Population variance known | Z-test |
| Large sample (n ≥ 30) | Z-test (approximately) |
| Small sample (n < 30) + normal population + unknown variance | T-test |
| Small sample + non-normal population | Non-parametric test |

### Common Confidence Levels

| Confidence Level | α | z_(α/2) |
|------------------|---|---------|
| 90% | 0.10 | 1.645 |
| 95% | 0.05 | 1.960 |
| 99% | 0.01 | 2.576 |

---

## Additional Resources

- [300Hours Quantitative Methods Cheat Sheet](https://300hours.com/cfa-level-1-quantitative-methods-cheat-sheet/) - Interactive web version
- [CFA Institute](https://www.cfainstitute.org/) - Official curriculum materials
- Practice using financial calculators (BA II Plus, HP 12C) for time value of money calculations

---

## Notes

- Always pay attention to whether you're working with population or sample statistics
- Check whether data is normally distributed before applying parametric tests
- For investment returns, use geometric mean rather than arithmetic mean for multi-period returns
- Remember that correlation does not imply causation
- When in doubt about test selection, check sample size and distribution assumptions

---

*Last Updated: March 2026*
*Knowledge absorbed from 300hours.com CFA Level 1 Quantitative Methods resources*
