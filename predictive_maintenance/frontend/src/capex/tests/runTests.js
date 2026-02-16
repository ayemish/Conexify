/**
 * Test Runner - Execute all tests from command line
 * Run with: node --experimental-vm-modules src/tests/runTests.js
 */

import { runAllUnitTests } from './unitTests.js';
import { runAllTests as runPipelineTests, testExternalDataIntegration } from './testPipeline.js';

console.log('\n');
console.log('╔════════════════════════════════════════════════════════════╗');
console.log('║        CAPEX GENERATOR - FULL TEST SUITE                   ║');
console.log('╚════════════════════════════════════════════════════════════╝');
console.log('\n');

console.log('Running Unit Tests...');
console.log('─'.repeat(60));
const unitResults = runAllUnitTests();

console.log('\n');
console.log('Running Pipeline Integration Tests...');
console.log('─'.repeat(60));
const pipelineResults = runPipelineTests();

console.log('\n');
console.log('Running External Data Integration Tests...');
console.log('─'.repeat(60));
const externalResults = testExternalDataIntegration();

console.log('\n');
console.log('╔════════════════════════════════════════════════════════════╗');
console.log('║                    FINAL REPORT                            ║');
console.log('╚════════════════════════════════════════════════════════════╝');

const totalPassed = unitResults.totalPassed + pipelineResults.passed;
const totalFailed = unitResults.totalFailed + pipelineResults.failed;
const total = totalPassed + totalFailed;

console.log(`\n  Unit Tests:     ${unitResults.totalPassed} passed, ${unitResults.totalFailed} failed`);
console.log(`  Pipeline Tests: ${pipelineResults.passed} passed, ${pipelineResults.failed} failed`);
console.log(`  ─────────────────────────────────────`);
console.log(`  TOTAL:          ${totalPassed} passed, ${totalFailed} failed (${total} tests)`);
console.log(`  Success Rate:   ${((totalPassed / total) * 100).toFixed(1)}%`);

if (externalResults.fddResult) {
  console.log(`\n  External Data Validation:`);
  console.log(`    - FDD Readings Generated: ${externalResults.fddData?.readings?.length || 0}`);
  console.log(`    - Faults Detected: ${externalResults.fddResult?.faults?.length || 0}`);
  console.log(`    - Survival Risk Category: ${externalResults.survivalResult?.riskCategory || 'N/A'}`);
}

console.log('\n' + '═'.repeat(60));

if (totalFailed === 0) {
  console.log('✓ ALL TESTS PASSED');
} else {
  console.log(`✗ ${totalFailed} TEST(S) FAILED`);
  process.exitCode = 1;
}

console.log('═'.repeat(60) + '\n');
