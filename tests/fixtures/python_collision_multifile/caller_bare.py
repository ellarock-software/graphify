import module_a
import module_b

def bare_caller():
    # Call the same bare function name from different modules
    # This should resolve based on module qualification, but currently doesn't
    result = process()  # Bare name - which process() does this call?
    return result
