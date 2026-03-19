const hre = require("hardhat");

async function main() {
  console.log("Deploying ConformationalRegistry...");

  const Registry = await hre.ethers.getContractFactory("ConformationalRegistry");
  const registry = await Registry.deploy();
  await registry.waitForDeployment();

  const address = await registry.getAddress();
  console.log(`ConformationalRegistry deployed to: ${address}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
