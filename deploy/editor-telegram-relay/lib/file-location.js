import {parseFileId} from '@mtcute/file-id';
// TDLib FileManager::from_persistent_id_v3 and FileLocation.hpp common layout.
// Newer Bot API file IDs use subversion 61; common document layout is unchanged.
export function parseDocument(fileId){
  const encoded=Buffer.from(fileId,'base64url');
  if(encoded.at(-1)!==4||encoded.at(-2)!==61)return parseFileId(fileId);
  const out=[];
  for(let i=0;i<encoded.length-2;i++){
    if(encoded[i]===0){const count=encoded[++i];if(!count||i>=encoded.length-2)throw new Error('Invalid file ID');out.push(...new Array(count).fill(0));}
    else out.push(encoded[i]);
  }
  const data=Buffer.from(out);let pos=8;
  const raw=data.readUInt32LE(0), type=raw&~0x03000000,dcId=data.readInt32LE(4);
  if(![2,4,5,8,9,10,13,17].includes(type)||raw&0x01000000||!(raw&0x02000000)||dcId<1||dcId>5)throw new Error('Unsupported document location');
  let size=data[pos++],header=1;
  if(size===254){size=data.readUIntLE(pos,3);pos+=3;header=4;}
  if(size<1||size>4096||pos+size>data.length)throw new Error('Invalid file reference');
  const fileReference=data.subarray(pos,pos+size);pos+=size+(4-(size+header)%4)%4;
  if(pos+16!==data.length)throw new Error('Invalid document location length');
  return {dcId,type,fileReference,location:{_:'common',id:data.readBigInt64LE(pos),accessHash:data.readBigInt64LE(pos+8)}};
}
