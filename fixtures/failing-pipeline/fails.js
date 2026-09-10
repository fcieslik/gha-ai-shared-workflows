const expectedStatus = "healthy";
const actualStatus = "unhealthy";

if (actualStatus !== expectedStatus) {
  throw new Error(
    `Intentional fixture failure: expected ${expectedStatus}, received ${actualStatus}.`,
  );
}
