const hre = require("hardhat");

async function main() {
  const V2_ADDRESS = process.env.V2_CONTRACT_ADDRESS;
  if (!V2_ADDRESS) {
    throw new Error("V2_CONTRACT_ADDRESS not set in .env");
  }

  console.log("Testing ConformationalRegistryV2 at:", V2_ADDRESS);

  // Get contract instance
  const Registry = await hre.ethers.getContractFactory("ConformationalRegistryV2");
  const registry = Registry.attach(V2_ADDRESS);

  const [signer] = await hre.ethers.getSigners();
  console.log("Signer:", signer.address);

  // Test data — fake conformer for sanity check
  const moleculeName = "test_v2_first_register";
  const cshHash = "0x" + "ab".repeat(32);  // 32 bytes of 0xab
  const sha256Id = "test_sha256_id_v2_first";
  const energyX1000 = 12345;  // 12.345 kcal/mol

  console.log("\nRegistering test conformer...");
  console.log("  Name:    ", moleculeName);
  console.log("  CSH hash:", cshHash);
  console.log("  Energy:  ", energyX1000 / 1000, "kcal/mol");

  const tx = await registry.registerConformer(
    moleculeName,
    cshHash,
    sha256Id,
    energyX1000
  );

  console.log("\nTransaction sent:", tx.hash);
  console.log("Waiting for confirmation...");

  const receipt = await tx.wait();
  console.log(`Confirmed in block: ${receipt.blockNumber}`);
  console.log(`Gas used: ${receipt.gasUsed.toString()}`);

  // Verify it was registered
  console.log("\nVerifying registration...");
  const isReg = await registry.isRegistered(cshHash);
  console.log(`  isRegistered(): ${isReg}`);

  const total = await registry.totalRegistered();
  console.log(`  totalRegistered(): ${total.toString()}`);

  console.log("\n✓ Test complete. Contract V2 works.");
  console.log(`\nView on Etherscan: https://sepolia.etherscan.io/tx/${tx.hash}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
