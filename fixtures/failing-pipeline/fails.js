const expectedStatus = "healthy";
const actualStatus = "unhealthy";

if (actualStatus !== expectedStatus) {
  // This is an intentional failure for testing purposes. Can you spot it?
  throw new Error(
    `Intentional fixture failure: expected ${expectedStatus}, received ${actualStatus}.`,
  );
}
