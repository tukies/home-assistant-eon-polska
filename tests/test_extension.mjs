import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {encodeSession, getSessionCode, HelperError} from '../browser-helper/session.mjs';

function api({url='https://eon.pl/mojeon', valid=true}={}) {
  let cookieReads=0;
  return {
    tabs: {query: async () => [{id:7,url}]},
    scripting: {executeScript: async () => [{result:valid}]},
    cookies: {
      getAllCookieStores: async () => [{id:'0',tabIds:[7]}],
      getAll: async query => {assert.equal(query.url,'https://eon.pl/mojeon/api/GetPHList');cookieReads++;return [{name:'.AspNet.Cookies',value:'synthetic'}];}
    },
    count: () => cookieReads
  };
}
test('code shape matches the Home Assistant decoder and excludes trackers', () => {
  const code=encodeSession([{name:'.AspNet.Cookies',value:'synthetic'},{name:'_ga',value:'private-tracking'}],'Browser');
  const data=JSON.parse(Buffer.from(code.split('.')[1],'base64url').toString());
  assert.deepEqual(data,{cookie:'.AspNet.Cookies=synthetic',user_agent:'Browser'});
});
test('only an authenticated E.ON tab can export',async()=>{
  const browser=api();assert.match(await getSessionCode(browser,'Browser'),/^EON_SESSION_V1\./);assert.equal(browser.count(),1);
});
test('unrelated sites cannot export cookies',async()=>{
  const browser=api({url:'https://example.com'});await assert.rejects(getSessionCode(browser,'Browser'),HelperError);assert.equal(browser.count(),0);
});
test('logged-out response cannot export cookies',async()=>{
  const browser=api({valid:false});await assert.rejects(getSessionCode(browser,'Browser'),HelperError);assert.equal(browser.count(),0);
});
test('missing session cookie is rejected',()=>assert.throws(()=>encodeSession([],'Browser'),HelperError));
test('header injection is rejected',()=>assert.throws(()=>encodeSession([{name:'.AspNet.Cookies',value:'x\r\nsecret'}],'Browser'),HelperError));
test('permissions have no other hosts, background collection or storage',()=>{
  const manifest=JSON.parse(readFileSync(new URL('../browser-helper/manifest.json',import.meta.url)));
  assert.deepEqual(manifest.host_permissions,['https://eon.pl/*']);
  assert.deepEqual(manifest.permissions,['cookies','scripting','clipboardWrite']);
  assert.equal(manifest.background,undefined);assert.equal(manifest.content_scripts,undefined);
});
test('the most-specific cookie is retained when names repeat',()=>{
  const code=encodeSession([{name:'.AspNet.Cookies',value:'specific'},{name:'.AspNet.Cookies',value:'general'}],'Browser');
  const data=JSON.parse(Buffer.from(code.split('.')[1],'base64url').toString());
  assert.equal(data.cookie,'.AspNet.Cookies=specific');
});
