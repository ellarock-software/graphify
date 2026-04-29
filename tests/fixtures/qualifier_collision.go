package main

// Two packages (simulated in same file for testing)
// pkg_a
func Process() string {
	return "pkg_a"
}

// pkg_b (different package)
func OtherFunc() string {
	return "pkg_b"
}

// main caller
func Caller() {
	// This should resolve using pkg qualifiers
	result := Process()
	_ = result
}
