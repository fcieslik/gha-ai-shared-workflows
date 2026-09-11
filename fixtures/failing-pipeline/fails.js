const cart = [
  { name: "Keyboard", price: "49.90", quantity: 1 },
  { name: "USB cable", price: "9.95", quantity: 2 },
];

function lineTotal(item) {
  return Number.parseFloat(item.price) * item.quantity;
}

function cartTotal(items) {
  return items.reduce((total, item) => total + lineTotal(item), 0);
}

const total = cartTotal(cart);
console.log(`Cart total: ${total.toFixed(2)}`);
