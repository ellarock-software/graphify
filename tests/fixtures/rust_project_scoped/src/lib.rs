// lib.rs - demonstrates namespace resolution for scoped calls
pub mod fixtures;
pub mod other;

pub fn run_test() {
    // This should resolve to fixtures::gemini_timeout, not other::gemini_timeout
    let timeout = fixtures::gemini_timeout();
    println!("Timeout: {}", timeout);
}

pub fn other_test() {
    // This calls a function that's defined locally
    print_msg();
}

fn print_msg() {
    println!("Message");
}
