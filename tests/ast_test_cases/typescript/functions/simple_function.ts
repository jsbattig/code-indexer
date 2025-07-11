function calculate(x: number, y: number): number {
    return x + y;
}

const processData = async (data: string[]): Promise<number[]> => {
    return data.map(item => item.length);
};

interface Calculator {
    add(a: number, b: number): number;
}

type Status = 'pending' | 'completed' | 'failed';