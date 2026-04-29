pub use error::Error;

mod error {
    pub struct Error;
    impl Error {
        pub fn new() -> Self {
            Error
        }
    }
}
