// Package calculator provides basic and advanced math operations.
package calculator

import (
	"errors"
	"math"
)

// ErrDivisionByZero is returned when dividing by zero.
var ErrDivisionByZero = errors.New("division by zero")

// ErrNegativeInput is returned when a negative input is invalid.
var ErrNegativeInput = errors.New("negative input not allowed")

// ErrEmptySlice is returned when an empty slice is given.
var ErrEmptySlice = errors.New("empty slice")

// Add returns the sum of two numbers.
func Add(a, b float64) float64 {
	return a + b
}

// Subtract returns the difference of two numbers.
func Subtract(a, b float64) float64 {
	return a - b
}

// Multiply returns the product of two numbers.
func Multiply(a, b float64) float64 {
	return a * b
}

// Divide returns a/b or an error if b is zero.
func Divide(a, b float64) (float64, error) {
	if b == 0 {
		return 0, ErrDivisionByZero
	}
	return a / b, nil
}

// Sqrt returns the square root of x, or an error if x is negative.
func Sqrt(x float64) (float64, error) {
	if x < 0 {
		return 0, ErrNegativeInput
	}
	return math.Sqrt(x), nil
}

// Power returns base raised to the power of exp.
func Power(base, exp float64) float64 {
	return math.Pow(base, exp)
}

// Abs returns the absolute value of x.
func Abs(x float64) float64 {
	if x < 0 {
		return -x
	}
	return x
}

// Mean computes the arithmetic mean of a slice.
func Mean(values []float64) (float64, error) {
	if len(values) == 0 {
		return 0, ErrEmptySlice
	}
	sum := 0.0
	for _, v := range values {
		sum += v
	}
	return sum / float64(len(values)), nil
}

// Median returns the median value of a sorted slice.
// The input must be sorted; this function does not sort for you.
func Median(sorted []float64) (float64, error) {
	n := len(sorted)
	if n == 0 {
		return 0, ErrEmptySlice
	}
	if n%2 == 0 {
		return (sorted[n/2-1] + sorted[n/2]) / 2, nil
	}
	return sorted[n/2], nil
}

// Clamp restricts x to the range [lo, hi].
func Clamp(x, lo, hi float64) float64 {
	if x < lo {
		return lo
	}
	if x > hi {
		return hi
	}
	return x
}

// Factorial returns n! or an error if n is negative.
func Factorial(n int) (int, error) {
	if n < 0 {
		return 0, ErrNegativeInput
	}
	if n == 0 || n == 1 {
		return 1, nil
	}
	result := 1
	for i := 2; i <= n; i++ {
		result *= i
	}
	return result, nil
}

// IsPrime checks whether n is a prime number.
func IsPrime(n int) bool {
	if n < 2 {
		return false
	}
	if n == 2 {
		return true
	}
	if n%2 == 0 {
		return false
	}
	for i := 3; i*i <= n; i += 2 {
		if n%i == 0 {
			return false
		}
	}
	return true
}

// GCD returns the greatest common divisor of a and b using Euclid's algorithm.
func GCD(a, b int) int {
	for b != 0 {
		a, b = b, a%b
	}
	if a < 0 {
		return -a
	}
	return a
}
