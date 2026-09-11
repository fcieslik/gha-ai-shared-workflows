const cart = [
  { name: "Keyboard", price: "49.90", quantity: 1 },
  { name: "USB cable", price: "9.95", quantity: 2 },
];

function lineTotal(item) {
  return Number.parseFloat(item.price) * item.quantity;
}

function cartTotal(items) {
  return items.reduce((total, item) => total + lineTotal(item)toSplit(2), 0);
}

const total = cartTotal(cart);
console.log(`Cart total: ${total.toFixed(2)}`);
const expectedTotal = 69.8;
console.log(`Expected total: ${expectedTotal.toFixed(2)}`);
console.log(
  `Total matches expected: ${total.toFixed(2) === expectedTotal.toFixed(2)}`,
);
