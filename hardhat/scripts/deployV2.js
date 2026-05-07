const hre = require("hardhat");

async function main() {
  console.log("=".repeat(60));
  console.log("Deploying ConformationalRegistryV2 to Sepolia");
  console.log("=".repeat(60));

  // Get deployer info
  const [deployer] = await hre.ethers.getSigners();
  const balance = await hre.ethers.provider.getBalance(deployer.address);

  console.log(`\nDeployer address: ${deployer.address}`);
  console.log(`Deployer balance: ${hre.ethers.formatEther(balance)} ETH`);

  if (balance === 0n) {
    throw new Error("Deployer balance is 0! Get testnet ETH from a faucet.");
  }

  // Deploy contract
  console.log("\nDeploying contract...");
  const Registry = await hre.ethers.getContractFactory("ConformationalRegistryV2");
  const registry = await Registry.deploy();

  console.log("Waiting for deployment confirmation...");
  await registry.waitForDeployment();

  const address = await registry.getAddress();
  const txHash = registry.deploymentTransaction().hash;

  console.log("\n" + "=".repeat(60));
  console.log("✓ Deployment successful");
  console.log("=".repeat(60));
  console.log(`Contract address:    ${address}`);
  console.log(`Deployment tx hash:  ${txHash}`);
  console.log(`Etherscan link:      https://sepolia.etherscan.io/address/${address}`);
  console.log("=".repeat(60));

  console.log("\nNext steps:");
  console.log(`1. Save this address to your .env file:`);
  console.log(`   V2_CONTRACT_ADDRESS=${address}`);
  console.log(`2. Wait ~1 minute for the contract to appear on Etherscan`);
  console.log(`3. (Optional) Verify the contract:`);
  console.log(`   npx hardhat verify --network sepolia ${address}`);
}

main().catch((error) => {
  console.error("\n✗ Deployment failed:");
  console.error(error);
  process.exitCode = 1;
});
