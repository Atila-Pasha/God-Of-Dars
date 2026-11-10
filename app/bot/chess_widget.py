"""Interactive chess board for Telegram's message widget sandbox."""

import json
import zlib
from datetime import UTC

from app.models.chess_game import ChessGame
from app.services.chess_service import board_for

HTML = """<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>
*{box-sizing:border-box}body{margin:0;background:transparent;color:var(--tg-theme-text-color,#edf5ff);font:13px system-ui,sans-serif}
.card{padding:11px;border-radius:18px;background:var(--tg-theme-secondary-bg-color,#182638);border:1px solid var(--tg-theme-button-color,#4a86cf)}
.head{display:flex;justify-content:space-between;align-items:center}.tag{font-size:10px;color:var(--tg-theme-hint-color,#abc)}h1{font-size:18px;margin:4px 0}.status{padding:7px;border-radius:9px;background:var(--tg-theme-bg-color,#102136);min-height:33px;text-align:center;font-weight:750}
.board{width:288px;height:288px;margin:9px auto;display:grid;grid-template-columns:repeat(8,1fr);grid-template-rows:repeat(8,1fr);border:2px solid #6b8da6;direction:ltr}.cell{min-width:0;min-height:0;padding:0;border:0;border-radius:0;font-size:30px;font-family:system-ui,'DejaVu Sans',sans-serif;line-height:1;display:flex;align-items:center;justify-content:center;touch-action:manipulation}.light{background:#e8e0c8}.dark{background:#87a8b8}.light.white{color:#425f7e}.dark.white{color:#fff}.cell.black{color:#111824}.cell.selected{background:#f3cd59}.cell.last{box-shadow:inset 0 0 0 3px #f5bb44}
@media(max-width:319px){.board{width:240px;height:240px}.cell{font-size:24px}}@media(max-width:259px){.board{width:176px;height:176px}.cell{font-size:20px}}@media(min-width:380px){.board{width:328px;height:328px}.cell{font-size:34px}}
.promotion{display:none;justify-content:center;gap:8px;margin:7px 0}.promotion.show{display:flex}.promotion button{width:45px;height:42px;border:1px solid var(--tg-theme-button-color,#4a86cf);border-radius:8px;background:var(--tg-theme-bg-color,#102136);color:var(--tg-theme-text-color,#fff);font-size:26px}.foot{display:flex;justify-content:space-between;gap:5px;color:var(--tg-theme-hint-color,#abc);font-size:11px}.clock{font-weight:bold;color:var(--tg-theme-button-color,#7eb7ff)}
</style></head><body><main class="card"><div class="head"><span class="tag">GOD OF DARS · CHESS</span><span>♟ شطرنج</span></div><h1>شطرنج</h1><div class="status" id="status">در حال بارگذاری…</div><div class="board" id="board"></div><div class="promotion" id="promotion"><button data-piece="q">♛</button><button data-piece="r">♜</button><button data-piece="b">♝</button><button data-piece="n">♞</button></div><div class="foot"><span id="mode"></span><span class="clock" id="clock"></span></div></main><script>
var T=window.TelegramWidget,S={},selected='',pending='',busy=false;var symbols={K:'♔',Q:'♕',R:'♖',B:'♗',N:'♘',P:'♙',k:'♚',q:'♛',r:'♜',b:'♝',n:'♞',p:'♟'};
function read(v){try{return JSON.parse(v||'{}')}catch(e){return {}}}
function me(){return T&&T.viewer&&T.viewer.id}
function pieces(){var out=[],rows=(S.fen||'').split(' ')[0].split('/');for(var r=0;r<8;r++){var row=rows[r]||'';for(var i=0;i<row.length;i++){var c=row[i];if(c>='1'&&c<='8')for(var n=0;n<Number(c);n++)out.push('');else out.push(c)}}return out}
function square(row,col,flipped){var rank=flipped?row:7-row,file=flipped?7-col:col;return 'abcdefgh'[file]+String(rank+1)}
function index(sq){return (8-Number(sq[1]))*8+'abcdefgh'.indexOf(sq[0])}
function own(piece){return piece&&(S.challenger===me()?piece===piece.toUpperCase():piece===piece.toLowerCase())}
function tick(){var el=document.getElementById('clock');el.textContent=S.status==='active'?Math.max(0,Math.ceil((S.deadline*1000-Date.now())/1000))+' ثانیه':'پایان بازی'}
function render(){var board=document.getElementById('board'),all=pieces(),flip=S.challenger!==me()&&S.mode!=='computer',last=S.last||'';board.innerHTML='';for(var r=0;r<8;r++)for(var c=0;c<8;c++){var sq=square(r,c,flip),piece=all[index(sq)]||'',b=document.createElement('button');b.type='button';b.dataset.sq=sq;b.textContent=symbols[piece]||'';b.className='cell '+((r+c)%2?'dark':'light')+(piece?(piece===piece.toUpperCase()?' white':' black'):'')+(selected===sq?' selected':'')+(last.indexOf(sq)>=0?' last':'');board.appendChild(b)}var active=S.status==='active',mine=S.turn===me(),label=active?(mine?'نوبت توئه · مهره و بعد خانهٔ مقصد را بزن':'نوبت حریفه'):S.status==='cancelled'?'بازی لغو شد':S.winner===null?'بازی مساوی شد':S.winner===me()?'بردی! 🎉':'باختی!';if(S.check&&active)label+=' · کیش!';document.getElementById('status').textContent=label;document.getElementById('mode').textContent=S.mode==='computer'?'بازی با ربات':S.mode==='wager'?'شرط: '+S.stake+' '+(S.currency==='coin'?'طلا':'الماس'):'بازی دوستانه';document.getElementById('promotion').className=pending?'promotion show':'promotion';tick()}
function send(uci){busy=true;pending='';render();T.request('chess:move:'+S.id+':'+uci).then(function(a){busy=false;var next=read(a.result);if(next.fen){S=next;selected='';render()}else{render();if(next.error)document.getElementById('status').textContent=next.error}},function(){busy=false;render();document.getElementById('status').textContent='ارتباط برقرار نشد؛ دوباره تلاش کن'})}
document.getElementById('board').addEventListener('click',function(e){var cell=e.target.closest('button');if(!cell||busy||pending||S.status!=='active'||S.turn!==me())return;var sq=cell.dataset.sq,all=pieces(),piece=all[index(sq)]||'';if(!selected){if(own(piece)){selected=sq;render()}return}if(sq===selected){selected='';render();return}if(own(piece)){selected=sq;render();return}var moving=all[index(selected)]||'';if(moving.toLowerCase()==='p'&&(sq[1]==='8'||sq[1]==='1')){pending=selected+sq;render();return}send(selected+sq)});
document.getElementById('promotion').addEventListener('click',function(e){var b=e.target.closest('button');if(b&&pending&&!busy)send(pending+b.dataset.piece)});
S=read(T&&T.chatData);if(T){T.onEvent('chatDataChanged',function(){var next=read(T.chatData);if(next.fen){S=next;selected='';pending='';render()}});if(typeof T.setResizeAnchor==='function')T.setResizeAnchor('top');T.ready()}render();setInterval(tick,1000);
</script></body></html>"""

assert len(HTML.encode()) <= 32_768 and len(zlib.compress(HTML.encode(), 9)) <= 4_096


def state_json(game: ChessGame, challenger_tg: int, opponent_tg: int | None) -> str:
    board = board_for(game)
    last = game.moves.split()[-1] if game.moves else ""
    return json.dumps(
        {
            "id": game.id,
            "fen": board.fen(),
            "last": last,
            "status": game.status,
            "turn": challenger_tg
            if game.turn_id == game.challenger_id
            else opponent_tg
            if game.turn_id == game.opponent_id
            else None,
            "winner": challenger_tg
            if game.winner_id == game.challenger_id
            else opponent_tg
            if game.winner_id == game.opponent_id
            else -1
            if game.winner_id == -1
            else None,
            "check": board.is_check(),
            "deadline": int(game.deadline_at.astimezone(UTC).timestamp())
            if game.deadline_at
            else 0,
            "mode": game.mode,
            "currency": game.stake_type,
            "stake": game.stake_amount,
            "challenger": challenger_tg,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
