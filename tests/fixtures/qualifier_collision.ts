// Two imported modules with same function name
export class ProcessorA {
  process() {
    return "ProcessorA";
  }
}

export class ProcessorB {
  process() {
    return "ProcessorB";
  }
}

// Caller that should use qualified object.method
const processorA = new ProcessorA();
const processorB = new ProcessorB();

function caller() {
  const resultA = processorA.process();  // Should be qualified to processorA.process()
  const resultB = processorB.process();  // Should be qualified to processorB.process()
  return [resultA, resultB];
}
