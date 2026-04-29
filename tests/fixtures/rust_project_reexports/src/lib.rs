// lib.rs - re-exports Error from error module
pub use crate::error::Error;

pub mod error {
    pub enum Error {
        NotFound,
        InvalidInput,
    }
}

pub mod client {
    use crate::Error;

    pub fn connect() -> Result<(), Error> {
        Err(Error::NotFound)
    }
}
