from module_a import process as process_a
from module_b import process as process_b

def caller():
    # This is unqualified at call time, but was imported with alias
    # The extractor sees bare 'process_a()' call
    result_a = process_a()
    result_b = process_b()
    return [result_a, result_b]
