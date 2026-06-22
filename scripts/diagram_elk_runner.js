#!/usr/bin/env node
"use strict";

const ELK = require("./vendor/elk.bundled.js");

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => {
  input += chunk;
});

process.stdin.on("end", async () => {
  try {
    const graph = JSON.parse(input);
    const elk = new ELK();
    const result = await elk.layout(graph);
    process.stdout.write(JSON.stringify(result));
  } catch (error) {
    process.stderr.write(error && error.stack ? error.stack : String(error));
    process.exit(1);
  }
});
