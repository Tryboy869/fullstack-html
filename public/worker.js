self.onmessage = (e) => {
    // Simule un calcul long et non-bloquant
    const number = e.data;
    let result = 0;
    // Une boucle plus complexe pour prendre un peu de temps
    for (let i = 0; i < number; i++) {
        result += Math.tan(Math.sqrt(i));
    }
    self.postMessage({ result: result });
};