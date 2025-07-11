function greet(name) {
    console.log("Hello, " + name);
    return true;
}

const multiply = (a, b) => {
    return a * b;
};

async function fetchData(url) {
    try {
        const response = await fetch(url);
        return await response.json();
    } catch (error) {
        console.error(error);
    }
}