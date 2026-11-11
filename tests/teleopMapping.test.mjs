import test from 'node:test';
import assert from 'node:assert/strict';
import {mapCustomerHand} from '../src/lib/teleopMapping.ts';
const anchor={x:.5,y:.5,spanDepth:0,robotX:0,robotY:0,robotZ:1};
test('approaching the customer camera moves forward, not downward',()=>{const h=mapCustomerHand({x:.5,y:.5,depth:.1},anchor);assert.ok(h.y<0);assert.ok(Math.abs(h.depth+.04)<1e-9);});
test('raising the hand raises robot height without changing forward position',()=>{const h=mapCustomerHand({x:.5,y:.4,depth:0},anchor);assert.equal(h.y,0);assert.ok(.96-h.depth>1);});
test('horizontal motion is reversed and neutral pose does not jump',()=>{assert.ok(mapCustomerHand({x:.6,y:.5},anchor).x<0);assert.equal(mapCustomerHand({x:.5,y:.5},anchor).x,0);});
