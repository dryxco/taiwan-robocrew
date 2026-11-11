import test from 'node:test';import assert from 'node:assert/strict';
import {assignHands} from '../src/lib/handAssignment.ts';
const hand=x=>Array.from({length:21},()=>({x,y:.5}));
const labels=[ [{categoryName:'Right',score:.95}], [{categoryName:'Right',score:.96}] ];
test('keeps two hands even when the model assigns the same handedness',()=>{const pair=assignHands([hand(.2),hand(.8)],labels);assert.equal(Object.keys(pair).length,2);assert.equal(pair.left.points[0].x,.2);assert.equal(pair.right.points[0].x,.8);});
test('keeps identity when duplicate-label detections reorder',()=>{const previous=assignHands([hand(.2),hand(.8)],labels);const pair=assignHands([hand(.79),hand(.21)],labels,previous);assert.equal(pair.left.points[0].x,.21);assert.equal(pair.right.points[0].x,.79);});
