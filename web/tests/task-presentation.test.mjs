import assert from 'node:assert/strict';
import { test } from 'node:test';
import { taskPresentation } from '../lib/task-presentation.ts';

test('milestone percentages cannot claim completion or invent a known stage', () => {
  assert.deepEqual(taskPresentation({ status: 'processing', progress: 100 }), { label: '处理中', step: -1, busy: true });
  assert.equal(taskPresentation({ status: 'processing', stage: 'pose_3d', progress: 66 }).step, 3);
  assert.equal(taskPresentation({ status: 'processing', stage: 'serializing', progress: 96 }).step, 4);
  assert.equal(taskPresentation({ status: 'completed' }).step, 5);
});
test('disconnection and failure stop animation and do not show completed stages', () => {
  for (const state of [taskPresentation({ status: 'failed', progress: 66 }), taskPresentation({ status: 'processing', stage: 'pose_3d' }, true)]) {
    assert.equal(state.busy, false);
    assert.equal(state.step, -1);
  }
  assert.equal(taskPresentation({ status: 'queued' }).step, -1);
  assert.equal(taskPresentation({ status: 'uploading' }).label, '上传中');
});
