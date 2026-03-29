package calculator

import (
	"errors"
	"math"
	"testing"
)

func TestAdd(t *testing.T) {
	tests := []struct {
		name string
		a, b float64
		want float64
	}{
		{"positive", 2, 3, 5},
		{"negative", -1, -2, -3},
		{"zero", 0, 0, 0},
		{"mixed", -5, 3, -2},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := Add(tt.a, tt.b)
			if got != tt.want {
				t.Errorf("Add(%v, %v) = %v, want %v", tt.a, tt.b, got, tt.want)
			}
		})
	}
}

func TestSubtract(t *testing.T) {
	tests := []struct {
		name string
		a, b float64
		want float64
	}{
		{"positive", 10, 4, 6},
		{"negative result", 3, 7, -4},
		{"zero", 5, 5, 0},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := Subtract(tt.a, tt.b)
			if got != tt.want {
				t.Errorf("Subtract(%v, %v) = %v, want %v", tt.a, tt.b, got, tt.want)
			}
		})
	}
}

func TestMultiply(t *testing.T) {
	tests := []struct {
		name string
		a, b float64
		want float64
	}{
		{"positive", 3, 4, 12},
		{"by zero", 5, 0, 0},
		{"negative", -3, 4, -12},
		{"both negative", -3, -4, 12},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := Multiply(tt.a, tt.b)
			if got != tt.want {
				t.Errorf("Multiply(%v, %v) = %v, want %v", tt.a, tt.b, got, tt.want)
			}
		})
	}
}

func TestDivide(t *testing.T) {
	t.Run("valid division", func(t *testing.T) {
		got, err := Divide(10, 2)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if got != 5.0 {
			t.Errorf("Divide(10, 2) = %v, want 5.0", got)
		}
	})

	t.Run("division by zero", func(t *testing.T) {
		_, err := Divide(10, 0)
		if !errors.Is(err, ErrDivisionByZero) {
			t.Errorf("Divide(10, 0) error = %v, want ErrDivisionByZero", err)
		}
	})
}

func TestSqrt(t *testing.T) {
	t.Run("perfect square", func(t *testing.T) {
		got, err := Sqrt(4)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if got != 2 {
			t.Errorf("Sqrt(4) = %v, want 2", got)
		}
	})

	t.Run("zero", func(t *testing.T) {
		got, err := Sqrt(0)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if got != 0 {
			t.Errorf("Sqrt(0) = %v, want 0", got)
		}
	})

	t.Run("negative returns error", func(t *testing.T) {
		_, err := Sqrt(-1)
		if !errors.Is(err, ErrNegativeInput) {
			t.Errorf("Sqrt(-1) error = %v, want ErrNegativeInput", err)
		}
	})
}

func TestPower(t *testing.T) {
	tests := []struct {
		name     string
		base     float64
		exp      float64
		want     float64
	}{
		{"square", 2, 2, 4},
		{"cube", 3, 3, 27},
		{"zero exp", 5, 0, 1},
		{"one exp", 7, 1, 7},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := Power(tt.base, tt.exp)
			if got != tt.want {
				t.Errorf("Power(%v, %v) = %v, want %v", tt.base, tt.exp, got, tt.want)
			}
		})
	}
}

func TestAbs(t *testing.T) {
	tests := []struct {
		name string
		x    float64
		want float64
	}{
		{"positive stays positive", 5.0, 5.0},
		{"negative becomes positive", -3.0, 3.0},
		{"zero", 0.0, 0.0},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := Abs(tt.x)
			if got != tt.want {
				t.Errorf("Abs(%v) = %v, want %v", tt.x, got, tt.want)
			}
		})
	}
}

func TestMean(t *testing.T) {
	t.Run("normal values", func(t *testing.T) {
		got, err := Mean([]float64{1, 2, 3, 4, 5})
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if got != 3.0 {
			t.Errorf("Mean([1..5]) = %v, want 3.0", got)
		}
	})

	t.Run("single value", func(t *testing.T) {
		got, err := Mean([]float64{42})
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if got != 42 {
			t.Errorf("Mean([42]) = %v, want 42", got)
		}
	})

	t.Run("empty slice", func(t *testing.T) {
		_, err := Mean([]float64{})
		if !errors.Is(err, ErrEmptySlice) {
			t.Errorf("Mean([]) error = %v, want ErrEmptySlice", err)
		}
	})
}

func TestMedian(t *testing.T) {
	t.Run("odd count", func(t *testing.T) {
		got, err := Median([]float64{1, 3, 5})
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if got != 3 {
			t.Errorf("Median([1,3,5]) = %v, want 3", got)
		}
	})

	t.Run("even count", func(t *testing.T) {
		got, err := Median([]float64{1, 2, 3, 4})
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if got != 2.5 {
			t.Errorf("Median([1,2,3,4]) = %v, want 2.5", got)
		}
	})

	t.Run("empty slice", func(t *testing.T) {
		_, err := Median([]float64{})
		if !errors.Is(err, ErrEmptySlice) {
			t.Errorf("Median([]) error = %v, want ErrEmptySlice", err)
		}
	})
}

func TestClamp(t *testing.T) {
	tests := []struct {
		name     string
		x, lo, hi float64
		want     float64
	}{
		{"within range", 5, 0, 10, 5},
		{"below min", -1, 0, 10, 0},
		{"above max", 15, 0, 10, 10},
		{"at min", 0, 0, 10, 0},
		{"at max", 10, 0, 10, 10},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := Clamp(tt.x, tt.lo, tt.hi)
			if got != tt.want {
				t.Errorf("Clamp(%v, %v, %v) = %v, want %v", tt.x, tt.lo, tt.hi, got, tt.want)
			}
		})
	}
}

func TestFactorial(t *testing.T) {
	tests := []struct {
		name string
		n    int
		want int
	}{
		{"zero", 0, 1},
		{"one", 1, 1},
		{"five", 5, 120},
		{"ten", 10, 3628800},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := Factorial(tt.n)
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got != tt.want {
				t.Errorf("Factorial(%d) = %d, want %d", tt.n, got, tt.want)
			}
		})
	}

	t.Run("negative returns error", func(t *testing.T) {
		_, err := Factorial(-1)
		if !errors.Is(err, ErrNegativeInput) {
			t.Errorf("Factorial(-1) error = %v, want ErrNegativeInput", err)
		}
	})
}

func TestIsPrime(t *testing.T) {
	tests := []struct {
		n    int
		want bool
	}{
		{0, false},
		{1, false},
		{2, true},
		{3, true},
		{4, false},
		{17, true},
		{25, false},
		{97, true},
	}
	for _, tt := range tests {
		got := IsPrime(tt.n)
		if got != tt.want {
			t.Errorf("IsPrime(%d) = %v, want %v", tt.n, got, tt.want)
		}
	}
}

func TestGCD(t *testing.T) {
	tests := []struct {
		name string
		a, b int
		want int
	}{
		{"coprime", 7, 13, 1},
		{"common factor", 12, 8, 4},
		{"equal", 5, 5, 5},
		{"one is zero", 0, 7, 7},
		{"negative input", -12, 8, 4},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := GCD(tt.a, tt.b)
			if got != tt.want {
				t.Errorf("GCD(%d, %d) = %d, want %d", tt.a, tt.b, got, tt.want)
			}
		})
	}
}

func TestSqrtPrecision(t *testing.T) {
	got, err := Sqrt(2)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	want := math.Sqrt(2)
	if math.Abs(got-want) > 1e-10 {
		t.Errorf("Sqrt(2) = %v, want %v (within 1e-10)", got, want)
	}
}
