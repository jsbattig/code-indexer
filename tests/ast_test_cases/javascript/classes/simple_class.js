class Calculator {
    constructor(name) {
        this.name = name;
    }

    add(a, b) {
        return a + b;
    }

    subtract(a, b) {
        return a - b;
    }
}

const utils = {
    formatName(first, last) {
        return `${first} ${last}`;
    },
    
    validateEmail: function(email) {
        return email.includes('@');
    }
};