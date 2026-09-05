// 共享契约一致性测试：前端消费端 contracts.ts 的校验与映射必须
// 与 shared/contracts/posture.json（contract_version 1.1）及后端契约一致。
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  validateContract,
  applyRemoteContract,
  isRemoteContractActive,
  contractVersion,
  matrixShape,
  sleepPosNames,
  actionToLabelId,
  mirrorAction,
  LOCAL_CONTRACT,
  ContractValidationError,
} from '../src/core/contracts.ts';
import { actionToSleepPos, SLEEP_POS_NAMES, ROWS, COLS, mirrorAction as typesMirror } from '../src/core/types.ts';

describe('内置契约（vendored shared/contracts/posture.json）', () => {
  it('版本号为 1.1', () => {
    assert.equal(contractVersion(), '1.1');
  });
  it('矩阵为 44×24、row_column 索引序', () => {
    assert.deepEqual(matrixShape(), { rows: 44, columns: 24 });
    assert.equal(LOCAL_CONTRACT.pressure_matrix.index_order, 'row_column');
  });
  it('睡姿中文名映射完整', () => {
    assert.deepEqual(sleepPosNames(), {
      0: '仰卧',
      1: '俯卧',
      2: '左侧卧',
      3: '右侧卧',
    });
  });
  it('动作 → 睡姿映射符合契约（含 excluded）', () => {
    assert.equal(actionToLabelId(1), 0);
    assert.equal(actionToLabelId(6), 0);
    assert.equal(actionToLabelId(7), 1);
    assert.equal(actionToLabelId(10), 2);
    assert.equal(actionToLabelId(16), 3);
    assert.equal(actionToLabelId(21), 3);
    assert.equal(actionToLabelId(0), null); // 空载
    assert.equal(actionToLabelId(22), null); // 动态序列
    assert.equal(actionToLabelId(99), null);
  });
  it('镜像动作对与契约一致', () => {
    assert.equal(mirrorAction(10), 16);
    assert.equal(mirrorAction(16), 10);
    assert.equal(mirrorAction(15), 21);
    assert.equal(mirrorAction(1), null); // 仰卧无镜像对
  });
});

describe('types.ts 与契约一致性', () => {
  it('SLEEP_POS_NAMES 由契约驱动且值正确', () => {
    assert.deepEqual(SLEEP_POS_NAMES, sleepPosNames());
  });
  it('actionToSleepPos 对全部 1-21 动作返回契约结果', () => {
    for (let a = 1; a <= 21; a++) {
      assert.equal(actionToSleepPos(a), actionToLabelId(a));
    }
    assert.equal(actionToSleepPos(0), null);
    assert.equal(actionToSleepPos(22), null);
  });
  it('types.mirrorAction 与契约一致', () => {
    for (let a = 0; a <= 21; a++) {
      assert.equal(typesMirror(a), mirrorAction(a));
    }
  });
  it('矩阵维度常量与契约一致', () => {
    assert.equal(ROWS, LOCAL_CONTRACT.pressure_matrix.rows);
    assert.equal(COLS, LOCAL_CONTRACT.pressure_matrix.columns);
  });
});

describe('validateContract 校验规则（对齐 backend/data_utils/contracts.py）', () => {
  const valid = () => structuredClone(LOCAL_CONTRACT as unknown as Record<string, unknown>);

  it('拒绝非对象根', () => {
    assert.throws(() => validateContract(null), ContractValidationError);
    assert.throws(() => validateContract([1, 2]), ContractValidationError);
  });
  it('拒绝缺失 contract_version', () => {
    const doc = valid();
    delete doc.contract_version;
    assert.throws(() => validateContract(doc), /contract_version/);
  });
  it('拒绝非正整数的矩阵维度', () => {
    const doc = valid();
    (doc.pressure_matrix as Record<string, unknown>).rows = 0;
    assert.throws(() => validateContract(doc), /positive integer/);
  });
  it('拒绝 row_column 之外的索引序', () => {
    const doc = valid();
    (doc.pressure_matrix as Record<string, unknown>).index_order = 'column_row';
    assert.throws(() => validateContract(doc), /matrix\[row\]\[column\]/);
  });
  it('拒绝重复睡姿 ID', () => {
    const doc = valid();
    const postures = structuredClone(doc.postures as Record<string, unknown>[]);
    postures.push({ ...postures[0] });
    doc.postures = postures;
    assert.throws(() => validateContract(doc), /Duplicate posture ID/);
  });
  it('拒绝缺失中文名', () => {
    const doc = valid();
    (doc.postures as Record<string, unknown>[])[0].name_zh = '';
    assert.throws(() => validateContract(doc), /non-empty names/);
  });
});

describe('applyRemoteContract 版本门禁', () => {
  it('同版本远端契约 → 替换生效', () => {
    const res = applyRemoteContract(structuredClone(LOCAL_CONTRACT));
    assert.equal(res.ok, true);
    assert.equal(isRemoteContractActive(), true);
  });
  it('版本不一致 → 拒绝且保持本地基线', () => {
    const foreign = structuredClone(LOCAL_CONTRACT) as unknown as Record<string, unknown>;
    foreign.contract_version = '9.9';
    const res = applyRemoteContract(foreign);
    assert.equal(res.ok, false);
    assert.equal(res.versionMismatch, true);
    assert.match(res.error ?? '', /9\.9/);
  });
  it('非法文档 → 拒绝且不抛异常', () => {
    const res = applyRemoteContract({ nonsense: true });
    assert.equal(res.ok, false);
  });
});
