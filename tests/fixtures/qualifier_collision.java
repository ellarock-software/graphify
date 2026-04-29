// Two classes with method 'process'
public class ProcessorA {
    public void process() {
        System.out.println("ProcessorA");
    }
}

class ProcessorB {
    public void process() {
        System.out.println("ProcessorB");
    }
}

// Caller
class Caller {
    public void run() {
        ProcessorA a = new ProcessorA();
        a.process();  // Should resolve to ProcessorA.process
    }
}
