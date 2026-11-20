import { TelegramClient, Api } from 'telegram';
import { StringSession } from 'telegram/sessions/index.js';
import bigInt from 'big-integer';
import { parseDocument } from '../lib/file-location.js';
import { createHash, createCipheriv, createDecipheriv, randomBytes, timingSafeEqual } from 'node:crypto';

export function seal(value) {
  const iv=randomBytes(12), key=createHash('sha256').update(process.env.RELAY_SECRET).digest();
  const cipher=createCipheriv('aes-256-gcm',key,iv);
  const data=Buffer.concat([cipher.update(value,'utf8'),cipher.final()]);
  return Buffer.concat([iv,cipher.getAuthTag(),data]).toString('base64url');
}
export function unseal(value) {
  const data=Buffer.from(value,'base64url'), decipher=createDecipheriv('aes-256-gcm',createHash('sha256').update(process.env.RELAY_SECRET).digest(),data.subarray(0,12));
  decipher.setAuthTag(data.subarray(12,28));
  return Buffer.concat([decipher.update(data.subarray(28)),decipher.final()]).toString('utf8');
}
export default async function handler(req,res) {
  const supplied=Buffer.from(String(req.headers['x-relay-secret']||'')), expected=Buffer.from(process.env.RELAY_SECRET||'');
  if(expected.length<32||supplied.length!==expected.length||!timingSafeEqual(supplied,expected))return res.status(401).end();
  if(req.method!=='POST')return res.status(405).end();
  if(!process.env.TELEGRAM_API_ID||!process.env.TELEGRAM_API_HASH)return res.status(503).json({error:'MTProto credentials are not configured'});
  let client;
  try {
    const {fileId,offset=0,length=1048576,session,probe=false}=req.body||{};
    if(!probe&&(!Number.isSafeInteger(offset)||offset<0||offset%524288!==0||!Number.isSafeInteger(length)||length<1||length>2097152||typeof fileId!=='string'))return res.status(400).json({error:'Invalid chunk request'});
    const parsed=probe?null:parseDocument(fileId);
    if(parsed&&(parsed.location?._!=='common'||!parsed.fileReference))return res.status(400).json({error:'Unsupported document file ID'});
    client=new TelegramClient(new StringSession(session?unseal(session):''),Number(process.env.TELEGRAM_API_ID),process.env.TELEGRAM_API_HASH,{connectionRetries:2,requestRetries:2,retryDelay:500,autoReconnect:false});
    client.setLogLevel('none');
    await client.start({botAuthToken:process.env.TELEGRAM_BOT_TOKEN,onError:()=>{}});
    res.setHeader('cache-control','no-store');
    res.setHeader('x-telegram-session',seal(client.session.save()));
    if(probe){const me=await client.getMe();return res.status(200).json({ok:true,username:me.username});}
    const location=new Api.InputDocumentFileLocation({id:bigInt(parsed.location.id.toString()),accessHash:bigInt(parsed.location.accessHash.toString()),fileReference:Buffer.from(parsed.fileReference),thumbSize:''});
    const chunks=[];let received=0;
    const iterator=client.iterDownload({file:location,offset:bigInt(offset),requestSize:524288,chunkSize:524288,limit:Math.ceil(length/524288),dcId:parsed.dcId});
    try{for await(const chunk of iterator){chunks.push(Buffer.from(chunk).subarray(0,length-received));received+=chunks.at(-1).length;if(received>=length)break;}}finally{await iterator.close();}
    const data=Buffer.concat(chunks);
    if(parsed.dcId!==client.session.dcId){
      const sender=await client.getSender(parsed.dcId),dc=await client.getDC(parsed.dcId,false);
      const downloadSession=new StringSession('');downloadSession.setDC(parsed.dcId,dc.ipAddress,dc.port);downloadSession.authKey=sender.authKey;
      res.setHeader('x-telegram-session',seal(downloadSession.save()));
    }
    res.setHeader('content-type','application/octet-stream');res.setHeader('x-content-sha256',createHash('sha256').update(data).digest('hex'));
    return res.status(200).send(data);
  }catch(error){
    const message=String(error?.errorMessage||error?.message||'Telegram download failed');
    return res.status(502).json({error:message.replace(/\b\d{8,}:[A-Za-z0-9_-]+\b/g,'[redacted]')});
  }finally{if(client)await client.destroy().catch(()=>{});}
}
