-- thanners on discord
-- 12/24/2023
-- this code creates the MSSB 'Savant Sliders' dashboards found at these links
-- https://public.tableau.com/app/profile/thanners./viz/MSSBSavantSliders/Dashboard12?publish=yes
-- https://public.tableau.com/app/profile/thanners./viz/MSSBSavantSliders-BigBalla/Dashboard12?publish=yes
-- https://public.tableau.com/app/profile/thanners./viz/MSSBSavantSliders-StarsOn/Dashboard12?publish=yes

-- Converted from a temp table to a MATERIALIZED CTE so the whole script is one
-- read-only SELECT. A Postgres read-only transaction forbids ALL CREATE/DROP
-- (temp tables included), so the original two-statement form cannot run under
-- default_transaction_read_only=on. AS MATERIALIZED preserves the single-
-- evaluation behaviour the temp table provided.
with data_temp as materialized (

select *, coalesce(secondary_result_of_contact_named, result_of_ab_named) event_name,
case when half_inning ='0' then away_username when half_inning ='1' then home_username end batter_username,
case when half_inning ='0' then home_username when half_inning ='1' then away_username end pitcher_username,
case when away_score > home_score then away_username 
     when away_score < home_score then home_username end winner_of_game
from(
select 
ga.game_id,
aru.username_lowercase away_username,
acap.away_captain,
hru.username_lowercase home_username,
hcap.home_captain,
to_char(to_timestamp(ga.date_time_start), 'YYYY-MM-DD HH:MI:SS') game_start_time,
to_char(to_timestamp(ga.date_time_end), 'YYYY-MM-DD HH:MI:SS') game_end_time,
case when ga.stadium_id='0' then 'Mario Stadium'
	 when ga.stadium_id='1' then 'Bowsers Castle'
     when ga.stadium_id='2' then 'Warios Palace'
     when ga.stadium_id='3' then 'Yoshis Island'
 	 when ga.stadium_id='4' then 'Peachs Garden'
	 when ga.stadium_id='5' then 'DKs Jungle'
     when ga.stadium_id='6' then 'Toy Field'
     else 'unknown stadium name'
     end stadium_name,
ga.away_score,
ga.home_score,
ga.innings_selected,
ga.innings_played,
case when ga.quitter ='0' then 'away quit'
     when ga.quitter ='1' then 'home quit'
     when ga.quitter ='255' then 'neither quit'
     else null end as quitter,
ga.version,
ts.name gametype,
gh.winner_incoming_elo,
gh.winner_result_elo,
gh.loser_incoming_elo,
gh.loser_result_elo,
ev.event_num,
ev.away_score current_away_score,
ev.home_score current_home_score,
ev.inning,
ev.half_inning,
ev.chem_links_ob,
ev.star_chance,
ev.away_stars,
ev.home_stars,
ev.pitcher_stamina,
ev.outs,
ev.balls,
ev.strikes,
case
    when ev.result_of_ab = '0' then 'none'
    when ev.result_of_ab = '1' then 'strikeout'
    when ev.result_of_ab = '2' then 'walk (bb)'
    when ev.result_of_ab = '3' then 'walk (hbp)'
    when ev.result_of_ab = '4' then 'out'
    when ev.result_of_ab = '5' then 'caught'
    when ev.result_of_ab = '6' then 'caught line drive'
    when ev.result_of_ab = '7' then 'single'
    when ev.result_of_ab = '8' then 'double'
    when ev.result_of_ab = '9' then 'triple'
    when ev.result_of_ab = '10' then 'HR'
    when ev.result_of_ab = '11' then 'rboe'
    when ev.result_of_ab = '12' then 'chem error'
    when ev.result_of_ab = '13' then 'bunt'
    when ev.result_of_ab = '14' then 'sacfly'
    when ev.result_of_ab = '15' then 'gidp'
    when ev.result_of_ab = '16' then 'foul catch'
        end result_of_ab_named,
ev.result_rbi,
pcgs.name_lowercase pitcher,
case when lower(pcgs.fielding_hand::text) ='false' then 'lefty' else 'righty' end as fielding_hand,
bcgs.name_lowercase batter,
case when lower(bcgs.batting_hand::text) ='false' then 'righty' else 'lefty' end as batting_hand,
ccgs.name_lowercase catcher,
ru1.name_lowercase runner_on_first,
case when ru1.result_base::text ='0' then 'runner on 1st now batting lol?'
     when ru1.result_base::text ='1' then 'runner on 1st still on 1st'
     when ru1.result_base::text ='2' then 'runner on 1st to 2nd'
     when ru1.result_base::text ='3' then 'runner on 1st to 3rd'
     when ru1.result_base::text ='4' then 'runner on 1st scored'
     when ru1.result_base::text ='255' then 'runner on 1st out'
     else ru1.result_base::text
     end runner_on_1st_result_base,
case when ru1.steal::text ='0' then 'no steal attempt'
     when ru1.steal::text ='2' then 'non-perfect steal'
     when ru1.steal::text ='3' then 'perfect steal'
     else ru1.steal::text
    end runner_on_1st_steal_name,
case when ru1.out_type::text ='0' then 'none'
     when ru1.out_type::text ='1' then 'caught (batter out)'
     when ru1.out_type::text ='2' then 'tag'
     when ru1.out_type::text ='3' then 'force'
     when ru1.out_type::text ='4' then 'tag up force'
     when ru1.out_type::text ='16' then 'strikeout'
     else ru1.out_type::text
    end runner_on_1st_out_type_name,
case when ru1.out_location::text ='0' then 'none'
     when ru1.out_location::text ='1' then 'heading to first'
     when ru1.out_location::text ='2' then 'heading to second'
     when ru1.out_location::text ='3' then 'heading to third'
     when ru1.out_location::text ='4' then 'heading to home'
     else ru1.out_location::text
    end runner_on_1st_out_location_name,

ru2.name_lowercase runner_on_second,
case when ru2.result_base::text ='0' then 'runner on 2nd now batting lol?'
     when ru2.result_base::text ='1' then 'runner on 2nd back to 1st'
     when ru2.result_base::text ='2' then 'runner on 2nd still on 2nd'
     when ru2.result_base::text ='3' then 'runner on 2nd to 3rd'
     when ru2.result_base::text ='4' then 'runner on 2nd scored'
     when ru2.result_base::text ='255' then 'runner on 2nd out'
     else ru2.result_base::text
     end runner_on_2nd_result_base,
case when ru2.steal::text ='0' then 'no steal attempt'
     when ru2.steal::text ='2' then 'non-perfect steal'
     when ru2.steal::text ='3' then 'perfect steal'
     else ru2.steal::text
    end runner_on_2nd_steal_name,
case when ru2.out_type::text ='0' then 'none'
     when ru2.out_type::text ='1' then 'caught (batter out)'
     when ru2.out_type::text ='2' then 'tag'
     when ru2.out_type::text ='3' then 'force'
     when ru2.out_type::text ='4' then 'tag up force'
     when ru2.out_type::text ='16' then 'strikeout'
     else ru2.out_type::text
    end runner_on_2nd_out_type_name,
case when ru2.out_location::text ='0' then 'none'
     when ru2.out_location::text ='1' then 'heading to first'
     when ru2.out_location::text ='2' then 'heading to second'
     when ru2.out_location::text ='3' then 'heading to third'
     when ru2.out_location::text ='4' then 'heading to home'
     else ru2.out_location::text
    end runner_on_2nd_out_location_name,

ru3.name_lowercase runner_on_third,
case when ru3.result_base::text ='0' then 'runner on 3rd now batting lol?'
     when ru3.result_base::text ='1' then 'runner on 3rd back to 1st'
     when ru3.result_base::text ='2' then 'runner on 3rd back to 2nd'
     when ru3.result_base::text ='3' then 'runner on 3rd still on 3rd'
     when ru3.result_base::text ='4' then 'runner on 3rd scored'
     when ru3.result_base::text ='255' then 'runner on 3rd out'
     else ru3.result_base::text
     end runner_on_3rd_result_base,
case when ru3.steal::text ='0' then 'no steal attempt'
     when ru3.steal::text ='2' then 'non-perfect steal'
     when ru3.steal::text ='3' then 'perfect steal'
     else ru3.steal::text
    end runner_on_3rd_steal_name,
case when ru3.out_type::text ='0' then 'none'
     when ru3.out_type::text ='1' then 'caught (batter out)'
     when ru3.out_type::text ='2' then 'tag'
     when ru3.out_type::text ='3' then 'force'
     when ru3.out_type::text ='4' then 'tag up force'
     when ru3.out_type::text ='16' then 'strikeout'
     else ru3.out_type::text
    end runner_on_3rd_out_type_name,
case when ru3.out_location::text ='0' then 'none'
     when ru3.out_location::text ='1' then 'heading to first'
     when ru3.out_location::text ='2' then 'heading to second'
     when ru3.out_location::text ='3' then 'heading to third'
     when ru3.out_location::text ='4' then 'heading to home'
     else ru3.out_location::text
    end runner_on_3rd_out_location_name,
case when ps.pitch_type::text ='0' then 'curve'
     when ps.pitch_type::text ='1' then 'charge'
     when ps.pitch_type::text ='2' then 'changeup'
     end as pitch_type,
case when ps.charge_pitch_type::text ='0' then 'N/A'
     when ps.charge_pitch_type::text ='2' then 'slider'
     when ps.charge_pitch_type::text ='3' then 'perfect'
     end as charge_pitch_type,
case when ps.star_pitch::text ='0' then 'no'
     when ps.star_pitch::text ='1' then 'yes'
     end as star_pitch,
ps.contact_summary_id,
ps.pitch_speed,
ps.ball_position_strikezone,
ps.in_strikezone,
ps.bat_x_contact_pos,
ps.bat_z_contact_pos,
case when ps.type_of_swing::text ='0' then 'none'
     when ps.type_of_swing::text ='1' then 'slap'
     when ps.type_of_swing::text ='2' then 'charge'
     when ps.type_of_swing::text ='3' then 'star'
     when ps.type_of_swing::text ='4' then 'bunt'
     else ps.type_of_swing::text
     end type_of_swing_name,
case when cs.type_of_contact::text ='0' then 'sour-left'
     when cs.type_of_contact::text ='1' then 'nice-left'
     when cs.type_of_contact::text ='2' then 'perfect'
     when cs.type_of_contact::text ='3' then 'nice-right'
     when cs.type_of_contact::text ='4' then 'sour-right'
     else cs.type_of_contact::text
     end type_of_contact_name,
cs.charge_power_up,
cs.charge_power_down,
cs.star_swing_five_star,
case when cs.input_direction_stick::text ='0' then 'none'  
  	 when cs.input_direction_stick::text ='1' then 'left'
     when cs.input_direction_stick::text ='2' then 'right' 
     when cs.input_direction_stick::text ='4' then 'down' 
     when cs.input_direction_stick::text ='5' then 'down and left' 
     when cs.input_direction_stick::text ='6' then 'down and right' 
     when cs.input_direction_stick::text ='8' then 'up' 
     when cs.input_direction_stick::text ='9' then 'up and left' 
     when cs.input_direction_stick::text ='10' then 'up and right'
  	 when cs.input_direction_stick::text ='14' then 'up and down and right lol?'
   	 else cs.input_direction_stick::text
  	 end stick_input,
case when cs.input_direction::text ='0' then 'none'  
  	 when cs.input_direction::text ='1' then 'towards batter'
     when cs.input_direction::text ='2' then 'away from batter' 
     end stick_input_relative,
cs.frame_of_swing_upon_contact,
cs.ball_vert_angle,
cs.ball_horiz_angle,
cs.ball_power,
cs.contact_absolute,
cs.contact_quality,
cs.rng1,
cs.rng2,
cs.rng3,
cs.ball_x_velocity,
cs.ball_x_contact_pos,
cs.ball_x_landing_pos,
cs.ball_y_velocity,
cs.ball_y_landing_pos,
cs.ball_z_velocity,
cs.ball_z_contact_pos,
cs.ball_z_landing_pos,
cs.ball_max_height,
cs.ball_hang_time,
case when cs.primary_result::text ='0' then 'out'  
  	 when cs.primary_result::text ='1' then 'foul'
     when cs.primary_result::text ='2' then 'fair'
     when cs.primary_result::text ='3' then 'fielded'
     when cs.primary_result::text ='4' then 'unknown' 
     else cs.primary_result::text
     end primary_result_of_contact_name,
case
    when cs.secondary_result::text in ('0','1','2','14','16') then 'out'
    when cs.secondary_result::text in ('3') then 'foul'
    when cs.secondary_result::text in ('7') then 'single'
    when cs.secondary_result::text in ('8') then 'double'
    when cs.secondary_result::text in ('9') then 'triple'
    when cs.secondary_result::text in ('10') then 'homerun'
    when cs.secondary_result::text in ('11', '12') then 'induced error'
    when cs.secondary_result::text in ('13') then 'bunt'
    when cs.secondary_result::text in ('15') then 'double play'
    end secondary_result_of_contact_named,
cs.id,
fs.name_lowercase fielder_name,
case when fs.position::text ='0' then 'p'
     when fs.position::text ='1' then 'c'
     when fs.position::text ='2' then '1b'
     when fs.position::text ='3' then '2b'
     when fs.position::text ='4' then '3b'
     when fs.position::text ='5' then 'ss'
     when fs.position::text ='6' then 'lf'
     when fs.position::text ='7' then 'cf'
     when fs.position::text ='8' then 'rf'
     else fs.position::text 
     end fielder_position,
case when fs.action::text ='0' then 'none'
     when fs.action::text ='2' then 'sliding'
     when fs.action::text ='3' then 'walljump'
     end fielder_action,
fs.jump,
case when fs.bobble::text ='0' then 'none'
     when fs.bobble::text ='1' then 'slide/stun lock' -- unsure if this one matters, no occurrence in data
     when fs.bobble::text ='2' then 'fumble'
     when fs.bobble::text ='3' then 'bobble'
     when fs.bobble::text ='4' then 'fireball'
     when fs.bobble::text ='16' then 'garlic'
     else fs.bobble::text
     end fielder_bobble,
fs.swap,
case when fs.manual_select::text ='0' then 'no selected character'
     when fs.manual_select::text ='1' then 'selected other character'
     when fs.manual_select::text ='2' then 'selected this character'
     end fielder_manual_select_name,
fs.fielder_x_pos,
fs.fielder_y_pos,
fs.fielder_z_pos


from game ga
left join rio_user aru on ga.away_player_id = aru.id
left join rio_user hru on ga.home_player_id = hru.id
left join game_history gh on ga.game_id = gh.game_id
left join tag_set ts on gh.tag_set_id = ts.id
left join event ev on ga.game_id = ev.game_id
left join (select a.id, a.fielding_hand, b.name_lowercase from character_game_summary a left join character b on a.char_id = b.char_id) pcgs on ev.pitcher_id = pcgs.id
left join (select a.id, a.batting_hand, b.name_lowercase from character_game_summary a left join character b on a.char_id = b.char_id) bcgs on ev.batter_id = bcgs.id
left join (select a.id, b.name_lowercase from character_game_summary a left join character b on a.char_id = b.char_id) ccgs on ev.catcher_id = ccgs.id
left join (select c.name_lowercase, a.id, a.initial_base, a.result_base, a.out_type, a.out_location, a.steal
           from runner a left join character_game_summary b on a.runner_character_game_summary_id = b.id left join character c on b.char_id = c.char_id)
           ru1 on ev.runner_on_1 = ru1.id
left join (select c.name_lowercase, a.id, a.initial_base, a.result_base, a.out_type, a.out_location, a.steal
           from runner a left join character_game_summary b on a.runner_character_game_summary_id = b.id left join character c on b.char_id = c.char_id)
           ru2 on ev.runner_on_2 = ru2.id
left join (select c.name_lowercase, a.id, a.initial_base, a.result_base, a.out_type, a.out_location, a.steal
           from runner a left join character_game_summary b on a.runner_character_game_summary_id = b.id left join character c on b.char_id = c.char_id)
           ru3 on ev.runner_on_3 = ru3.id
inner join (select ga.game_id, ga.away_player_id, ch.name_lowercase away_captain from game ga
            inner join rio_user ru on ga.away_player_id = ru.id
            inner join character_game_summary cg on ga.game_id = cg.game_id
                                   and ru.id = cg.user_id
            left join character ch on ch.char_id = cg.char_id
            where cg.captain IS TRUE) acap on acap.away_player_id = aru.id 
                                           and acap.game_id = ev.game_id
inner join (select ga.game_id, ga.home_player_id, ch.name_lowercase home_captain from game ga
            inner join rio_user ru on ga.home_player_id = ru.id
            inner join character_game_summary cg on ga.game_id = cg.game_id
                                   and ru.id = cg.user_id
            left join character ch on ch.char_id = cg.char_id
            where cg.captain IS TRUE) hcap on hcap.home_player_id = hru.id
                                           and hcap.game_id = ev.game_id
left join pitch_summary ps on ev.pitch_summary_id = ps.id
left join contact_summary cs on ps.contact_summary_id = cs.id
left join (select a.*, c.name_lowercase from fielding_summary a left join character_game_summary b
           on a.fielder_character_game_summary_id = b.id left join character c
           on b.char_id = c.char_id) fs on cs.fielding_summary_id = fs.id
where to_char(to_timestamp(ga.date_time_start), 'YYYY-MM-DD HH:MI:SS')::date between '2023-06-01' and '2023-12-31'
and lower(name) in ('stars off, season 7')
order by game_id asc, ev.event_num asc
)a
)

select d1.pitcher_username, d2.batter_username, 
d1.barpercent as pitcher_barrels_given,
d1.rank as pitcher_barrel_percentile,
d2.barpercent as batter_barrels,
d2.rank as batter_barrel_percentile,
d3.chasepercent as batter_chase,
d3.rank as batter_chase_percentile,
d4.watchpercent as batter_watch,
d4.rank as batter_watch_percentile,
d5.whiffpercent as batter_whiff,
d5.rank as batter_whiff_percentile,
d6.whiffpercent as pitcher_whiff,
d6.rank as pitcher_whiff_percentile,
d7.ozonecontactpercent as batter_ozonecontact,
d7.rank as batter_ozone_contact_percentile,
-- d8.leanpercent as batter_leanpercent,
-- d8.rank as batter_lean_percentile,
d9.gamesplayed as user_gamesplayed,
d9.rank as user_gamesplayed_percentile,
d10.batterkpercent as batter_kpercent,
d10.rank as batterk_percentile,
d11.pitcherkpercent as pitcher_kpercent,
d11.rank as pitcher_k_percentile, -- was a duplicate of batterk_percentile (repo bug)
d12.bowserhrpercent as batter_bowserhrpercent,
d12.rank as batter_bowserhr_percentile,
d13.bowserhrpercent as pitcher_bowserhrpercent,
d13.rank as pitcher_bowserhr_percentile,
d14.maxelo as max_elo,
d14.rank as maxelo_percentile,
d15.kbhrpercent as kbhr_percent,
d15.rank as kbhr_percentile,
d16.goodtimingpercent as charge_timing_percent,
d16.rank as charge_timing_percentile,
d17.goodtimingpercent as slap_timing_percent,
d17.rank as slap_timing_percentile

from(
select pitcher_username, barpercent, 
(1-(percent_rank() over(order by barpercent)))*100::dec as rank
from(
select pitcher_username, barrels/total_contacts::dec as barpercent from(
select pitcher_username, 
sum(case when type_of_contact_name in ('nice-left','nice-right','perfect')
then 1 else 0 end) barrels,
sum(case when type_of_contact_name in ('nice-left','nice-right','perfect','sour-left','sour-right')
then 1 else 0 end) total_contacts
from data_temp where contact_summary_id is not null
group by 1 
having sum(case when type_of_contact_name in ('nice-left','nice-right','perfect','sour-left','sour-right')
then 1 else 0 end) >200
)b
)c
)d1
left join(
select batter_username, barpercent, 
(percent_rank() over(order by barpercent))*100::dec as rank
from(
select batter_username, barrels/total_contacts::dec as barpercent from(
select batter_username, 
sum(case when type_of_contact_name in ('nice-left','nice-right','perfect')
then 1 else 0 end) barrels,
sum(case when type_of_contact_name in ('nice-left','nice-right','perfect','sour-left','sour-right')
then 1 else 0 end) total_contacts
from data_temp where contact_summary_id is not null
group by 1 
having sum(case when type_of_contact_name in ('nice-left','nice-right','perfect','sour-left','sour-right')
then 1 else 0 end) >200
)b
)c
)d2 on d1.pitcher_username = d2.batter_username
left join(
select batter_username, chasepercent, 
(1-(percent_rank() over(order by chasepercent)))*100::dec as rank
from(
select batter_username, chase/total_pitches::dec as chasepercent from(
select batter_username, 
sum(case when type_of_swing_name not in ('none') and type_of_swing_name is not null 
then 1 else 0 end) chase,
count(*) as total_pitches
from data_temp where in_strikezone is false
group by 1 
having sum(case when type_of_swing_name not in ('none') and type_of_swing_name is not null 
then 1 else 0 end) >50
)b
)c
)d3 on d1.pitcher_username = d3.batter_username
left join(
select batter_username, watchpercent, 
(1-(percent_rank() over(order by watchpercent)))*100::dec as rank
from(
select batter_username, watch/total_pitches::dec as watchpercent from(
select batter_username, 
sum(case when type_of_swing_name in ('none') or type_of_swing_name is null 
then 1 else 0 end) watch,
count(*) as total_pitches
from data_temp where in_strikezone is true
group by 1 
having sum(case when type_of_swing_name in ('none') or type_of_swing_name is null 
then 1 else 0 end) >50
)b
)c
)d4 on d1.pitcher_username = d4.batter_username
left join(
select batter_username, whiffpercent, 
(1-(percent_rank() over(order by whiffpercent)))*100::dec as rank
from(
select batter_username, whiff/total_pitches::dec as whiffpercent from(
select batter_username, 
sum(case when type_of_swing_name not in ('none') and contact_summary_id is null
then 1 else 0 end) whiff,
count(*) as total_pitches
from data_temp where type_of_swing_name not in ('none')
group by 1 
having sum(case when type_of_swing_name not in ('none') and contact_summary_id is null
then 1 else 0 end) >50
)b
)c
)d5 on d1.pitcher_username = d5.batter_username
left join(
select pitcher_username, whiffpercent, 
(percent_rank() over(order by whiffpercent))*100::dec as rank
from(
select pitcher_username, whiff/total_pitches::dec as whiffpercent from(
select pitcher_username, 
sum(case when type_of_swing_name not in ('none') and contact_summary_id is null
then 1 else 0 end) whiff,
count(*) as total_pitches
from data_temp where type_of_swing_name not in ('none')
group by 1 
having sum(case when type_of_swing_name not in ('none') and contact_summary_id is null
then 1 else 0 end) >50
)b
)c
)d6 on d1.pitcher_username = d6.pitcher_username
left join(
select batter_username, ozonecontactpercent, 
(percent_rank() over(order by ozonecontactpercent))*100::dec as rank
from(
select batter_username, ozonecontact/total_pitches::dec as ozonecontactpercent from(
select batter_username, 
sum(case when type_of_swing_name not in ('none') and contact_summary_id is not null
then 1 else 0 end) ozonecontact,
count(*) as total_pitches
from data_temp where in_strikezone is false and type_of_swing_name not in ('none')
group by 1 
having sum(case when type_of_swing_name not in ('none') and contact_summary_id is not null
then 1 else 0 end) >50
)b
)c
)d7 on d1.pitcher_username = d7.batter_username
-- left join(
-- select batter_username, leanpercent, 
-- (percent_rank() over(order by leanpercent))*100::dec as rank
-- from(
-- select batter_username, lean/total_abs::dec as leanpercent from(
-- select batter_username, 
-- sum(case when result_of_ab_named in ('walk (hbp)')
-- then 1 else 0 end) lean,
-- count(*) as total_abs
-- from data_temp where result_of_ab_named not in ('none')
-- and batter not in ('bowser', 'petey', 'bro(h)', 'bro(b)', 'bro(f)')
-- group by 1 
-- having sum(case when result_of_ab_named in ('walk (hbp)')
-- then 1 else 0 end) >0
-- )b
-- )c
-- )d8 on d1.pitcher_username = d8.batter_username
left join(
select batter_username, gamesplayed, 
(percent_rank() over(order by gamesplayed))*100::dec as rank
from(
select batter_username, games as gamesplayed from(
select batter_username, 
count(distinct game_id) games
from data_temp
group by 1
)b
)c
)d9 on d1.pitcher_username = d9.batter_username
left join(
select batter_username, batterkpercent, 
(1-(percent_rank() over(order by batterkpercent)))*100::dec as rank
from(
select batter_username, batterk/total_abs::dec as batterkpercent from(
select batter_username, 
sum(case when result_of_ab_named in ('strikeout')
then 1 else 0 end) batterk,
count(*) as total_abs
from data_temp where result_of_ab_named not in ('none')
group by 1 
having sum(case when result_of_ab_named in ('strikeout')
then 1 else 0 end) >50
)b
)c
)d10 on d1.pitcher_username = d10.batter_username
left join(
select pitcher_username, pitcherkpercent, 
(percent_rank() over(order by pitcherkpercent))*100::dec as rank
from(
select pitcher_username, batterk/total_abs::dec as pitcherkpercent from(
select pitcher_username, 
sum(case when result_of_ab_named in ('strikeout')
then 1 else 0 end) batterk,
count(*) as total_abs
from data_temp where result_of_ab_named not in ('none')
group by 1 
having sum(case when result_of_ab_named in ('strikeout')
then 1 else 0 end) >50
)b
)c
)d11 on d1.pitcher_username = d11.pitcher_username
left join( -- NOTE: no batter character filter -- this is overall HR rate, not Bowser's
select batter_username, bowserhrpercent, 
(percent_rank() over(order by bowserhrpercent))*100::dec as rank
from(
select batter_username, bowserhr/total_abs::dec as bowserhrpercent from(
select batter_username, 
sum(case when result_of_ab_named in ('HR')
then 1 else 0 end) bowserhr,
count(*) as total_abs
from data_temp where result_of_ab_named not in ('none', 'walk (hbp)', 'walk (bb)')
group by 1 
having sum(case when result_of_ab_named in ('HR')
then 1 else 0 end) >5
)b
)c
)d12 on d1.pitcher_username = d12.batter_username
left join( -- NOTE: no batter character filter -- this is overall HR allowed, not Bowser's
select pitcher_username, bowserhrpercent, 
(1-(percent_rank() over(order by bowserhrpercent)))*100::dec as rank
from(
select pitcher_username, bowserhr/total_abs::dec as bowserhrpercent from(
select pitcher_username, 
sum(case when result_of_ab_named in ('HR')
then 1 else 0 end) bowserhr,
count(*) as total_abs
from data_temp where result_of_ab_named not in ('none', 'walk (hbp)', 'walk (bb)')
group by 1 
having sum(case when result_of_ab_named in ('HR')
then 1 else 0 end) >5
)b
)c
)d13 on d1.pitcher_username = d13.pitcher_username
left join(
select winner_of_game, maxelo, 
(percent_rank() over(order by maxelo))*100::dec as rank
from(
select winner_of_game, maxelo as maxelo from(
select winner_of_game, 
max(winner_result_elo) maxelo
from data_temp
group by 1
)b
)c
)d14 on d1.pitcher_username = d14.winner_of_game
left join( -- star-swing HR rate, excludes Peach's Garden. NOTE: no King Boo filter --
       -- this is every character's star swing, not King Boo's
select batter_username, kbhrpercent, 
(percent_rank() over(order by kbhrpercent))*100::dec as rank
from(
select batter_username, kbhr/total_star_swings::dec as kbhrpercent from(
select batter_username, 
sum(case when result_of_ab_named in ('HR')
then 1 else 0 end) kbhr,
count(*) as total_star_swings
from data_temp where type_of_swing_name ='star'
and stadium_name not in ('Peachs Garden')
group by 1 
having sum(case when result_of_ab_named in ('HR')
then 1 else 0 end) >5
)b
)c
)d15 on d1.pitcher_username = d15.batter_username
left join( -- timing on charge swings with pull dependent power hitters (bro, bowser, petey, pianta, DK) 7-8-9
select batter_username, goodtimingpercent, 
(percent_rank() over(order by goodtimingpercent))*100::dec as rank
from(
select batter_username, good_timing/total_swings::dec as goodtimingpercent from(
select batter_username, 
sum(case when frame_of_swing_upon_contact in ('7','8','9')
then 1 else 0 end) good_timing,
count(*) as total_swings
from data_temp where type_of_swing_name in ('charge')
and frame_of_swing_upon_contact in ('2','3','4','5','6','7','8','9','10')
and lower(batter) in('bro(h)','bro(f)','bro(b)','bowser','petey','pianta(r)','pianta(y)','pianta(b)','dk')
group by 1 
having sum(case when frame_of_swing_upon_contact in ('7','8','9')
then 1 else 0 end) >10
)b
)c
)d16 on d1.pitcher_username = d16.batter_username
left join( -- timing on slap (3,4,5)
select batter_username, goodtimingpercent, 
(percent_rank() over(order by goodtimingpercent))*100::dec as rank
from(
select batter_username, good_timing/total_swings::dec as goodtimingpercent from(
select batter_username, 
sum(case when frame_of_swing_upon_contact in ('3','4','5')
then 1 else 0 end) good_timing,
count(*) as total_swings
from data_temp where type_of_swing_name in ('slap')
and frame_of_swing_upon_contact in ('2','3','4','5','6','7','8','9','10')
group by 1 
having sum(case when frame_of_swing_upon_contact in ('3','4','5')
then 1 else 0 end) >25
)b
)c
)d17 on d1.pitcher_username = d17.batter_username
;